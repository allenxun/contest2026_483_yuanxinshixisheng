package cn.yuanxin.mvp.web.assessments;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** M3-A01 受理（真实 PG）：事务落库、T13 幂等、占用互斥、并发、替换语义。 */
class AssessmentAcceptanceIT extends AssessmentTestSupport {

    @Test
    @DisplayName("A01 happy：202 + T05/T03/T11/T12/T13 全部落库")
    void happyPath() throws Exception {
        GimbalFixture gimbal = createGimbal();
        String key = "d-a01-happy-" + UUID.randomUUID();
        MvcResult r = postA01(gimbal.token(), key);
        assertEquals(202, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode body = JSON.readTree(r.getResponse().getContentAsString());
        assertFalse(body.path("meta").path("replayed").asBoolean(true));
        JsonNode d = body.path("data");
        UUID taskId = UUID.fromString(d.path("taskId").asText());
        assertEquals("queued", d.path("status").asText());
        assertEquals("1", d.path("photoVersion").asText());
        assertEquals("1", d.path("currentAssessmentRevision").asText());

        Map<String, Object> t05 = jdbc.queryForMap(
                "SELECT status, current_photo_version, processing_revision, gimbal_id::text AS gid,"
                        + " source_request_id, photo_versions::text AS pv FROM skin_assessments"
                        + " WHERE id = ?", taskId);
        assertEquals("queued", t05.get("status"));
        assertEquals(1L, ((Number) t05.get("current_photo_version")).longValue());
        assertEquals(1L, ((Number) t05.get("processing_revision")).longValue());
        assertEquals(gimbal.gimbalId().toString(), t05.get("gid"));
        JsonNode versions = JSON.readTree((String) t05.get("pv")).path("versions");
        assertEquals(1, versions.size());
        JsonNode images = versions.get(0).path("images");
        assertTrue(images.has("front") && images.has("left") && images.has("right"));

        Map<String, Object> t03 = jdbc.queryForMap(
                "SELECT current_assessment_id::text AS cid, current_assessment_revision AS rev"
                        + " FROM gimbals WHERE id = ?", gimbal.gimbalId());
        assertEquals(taskId.toString(), t03.get("cid"));
        assertEquals(1L, ((Number) t03.get("rev")).longValue());

        List<Map<String, Object>> media = jdbc.queryForList(
                "SELECT id::text AS id, photo_version, state, purpose FROM media_objects"
                        + " WHERE assessment_id = ?", taskId);
        assertEquals(3, media.size());
        for (Map<String, Object> m : media) {
            assertEquals(1L, ((Number) m.get("photo_version")).longValue());
            assertEquals("available", m.get("state"));
            assertEquals("assessment_source", m.get("purpose"));
        }

        Map<String, Object> job = jdbc.queryForMap(
                "SELECT job_type, owner_type, owner_id::text AS owner_id, input_revision, dedup_key,"
                        + " payload->>'schema_version' AS sv FROM async_jobs WHERE owner_id = ?",
                taskId);
        assertEquals("assessment.analyze", job.get("job_type"));
        assertEquals("assessment", job.get("owner_type"));
        assertEquals(taskId.toString(), job.get("owner_id"));
        assertEquals(1L, ((Number) job.get("input_revision")).longValue());
        assertEquals("assessment:" + taskId + ":1", job.get("dedup_key"));
        assertEquals("1", job.get("sv"));

        Map<String, Object> t13 = jdbc.queryForMap(
                "SELECT status, resource_type, resource_id::text AS rid FROM idempotency_requests"
                        + " WHERE principal_type='gimbal' AND principal_id = ?",
                gimbal.gimbalId().toString());
        assertEquals("succeeded", t13.get("status"));
        assertEquals("skin_assessment", t13.get("resource_type"));
        assertEquals(taskId.toString(), t13.get("rid"));
    }

    @Test
    @DisplayName("A01 同键同内容重放：200 replayed，无新行，指针不变")
    void replaySameKeySameContent() throws Exception {
        GimbalFixture gimbal = createGimbal();
        String key = "d-a01-replay-" + UUID.randomUUID();
        UUID taskId = acceptA01(gimbal, key);
        int beforeJobs = count("SELECT count(*) FROM async_jobs WHERE owner_id = ?", taskId);

        MvcResult replay = postA01(gimbal.token(), key);
        assertEquals(200, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        JsonNode body = JSON.readTree(replay.getResponse().getContentAsString());
        assertTrue(body.path("meta").path("replayed").asBoolean());
        assertEquals(taskId.toString(), body.path("data").path("taskId").asText());
        assertEquals("queued", body.path("data").path("status").asText());
        assertEquals("1", body.path("data").path("photoVersion").asText());

        assertEquals(1, count("SELECT count(*) FROM skin_assessments WHERE id = ?", taskId));
        assertEquals(3, count("SELECT count(*) FROM media_objects WHERE assessment_id = ?", taskId));
        assertEquals(beforeJobs, count("SELECT count(*) FROM async_jobs WHERE owner_id = ?", taskId));
        assertEquals(1L, jdbc.queryForObject(
                "SELECT current_assessment_revision FROM gimbals WHERE id = ?", Long.class,
                gimbal.gimbalId()));
    }

    @Test
    @DisplayName("A01 同键不同内容：409 IDEMPOTENCY_CONTENT_CONFLICT")
    void sameKeyDifferentContent() throws Exception {
        GimbalFixture gimbal = createGimbal();
        String key = "d-a01-conflict-" + UUID.randomUUID();
        acceptA01(gimbal, key);
        MvcResult r = postA01(gimbal.token(), key, a01Metadata(), png(9), png(2), png(3));
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("IDEMPOTENCY_CONTENT_CONFLICT", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A01 APP token → 403 CALLER_NOT_ALLOWED")
    void appForbidden() throws Exception {
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a01-app");
        MvcResult r = postA01(app.accessToken(), "d-a01-app-" + UUID.randomUUID());
        assertEquals(403, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("CALLER_NOT_ALLOWED", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A01 缺 Idempotency-Key → 400")
    void missingIdempotencyKey() throws Exception {
        GimbalFixture gimbal = createGimbal();
        MvcResult r = mockMvc.perform(
                        org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                                .multipart("/api/v1/skin-assessment-tasks")
                                .file(jsonPart("metadata", a01Metadata()))
                                .file(imagePart("front", png(1)))
                                .file(imagePart("left", png(2)))
                                .file(imagePart("right", png(3)))
                                .header("Authorization", "Bearer " + gimbal.token()))
                .andReturn();
        assertEquals(400, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A01 缺图片 part / 未知 metadata 字段 / photoVersion!=1 → 400")
    void invalidInputs() throws Exception {
        GimbalFixture gimbal = createGimbal();
        MvcResult missing = mockMvc.perform(
                        org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                                .multipart("/api/v1/skin-assessment-tasks")
                                .file(jsonPart("metadata", a01Metadata()))
                                .file(imagePart("front", png(1)))
                                .file(imagePart("left", png(2)))
                                .header("Authorization", "Bearer " + gimbal.token())
                                .header("Idempotency-Key", "d-a01-" + UUID.randomUUID()))
                .andReturn();
        assertEquals(400, missing.getResponse().getStatus());
        assertEquals("INVALID_INPUT", error(missing).path("code").asText());

        MvcResult unknown = postA01(gimbal.token(), "d-a01-" + UUID.randomUUID(),
                "{\"photoVersion\":\"1\",\"captureSessionId\":\"cs\","
                        + "\"consentEvidenceRef\":\"ce\",\"extra\":1}", png(1), png(2), png(3));
        assertEquals(400, unknown.getResponse().getStatus(), unknown.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(unknown).path("code").asText());

        MvcResult badVersion = postA01(gimbal.token(), "d-a01-" + UUID.randomUUID(),
                "{\"photoVersion\":\"2\",\"captureSessionId\":\"cs\","
                        + "\"consentEvidenceRef\":\"ce\"}", png(1), png(2), png(3));
        assertEquals(400, badVersion.getResponse().getStatus());
        assertEquals("INVALID_INPUT", error(badVersion).path("code").asText());
    }

    @Test
    @DisplayName("A01 非图片字节 → 415 UNSUPPORTED_IMAGE")
    void nonImageBytes() throws Exception {
        GimbalFixture gimbal = createGimbal();
        MvcResult r = postA01(gimbal.token(), "d-a01-" + UUID.randomUUID(), a01Metadata(),
                new byte[]{1, 2, 3, 4, 5, 6, 7, 8}, png(2), png(3));
        assertEquals(415, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("UNSUPPORTED_IMAGE", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A01 running 执行占用 → 409 DEVICE_OCCUPIED，无 T05/T03/T12 写，T13 rejected 可重放")
    void openRunningExecution() throws Exception {
        GimbalFixture gimbal = createGimbal();
        seedOpenExecution(gimbal.gimbalId(), "running");
        long beforeT05 = count("SELECT count(*) FROM skin_assessments WHERE gimbal_id = ?",
                gimbal.gimbalId());
        String key = "d-a01-occupied-" + UUID.randomUUID();
        MvcResult r = postA01(gimbal.token(), key);
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("DEVICE_OCCUPIED", error(r).path("code").asText());
        assertEquals(beforeT05, count("SELECT count(*) FROM skin_assessments WHERE gimbal_id = ?",
                gimbal.gimbalId()));
        assertNull(jdbc.queryForObject(
                "SELECT current_assessment_id FROM gimbals WHERE id = ?", UUID.class,
                gimbal.gimbalId()));
        // 不得新建分析任务（media.cleanup 补偿任务不计入此断言）
        assertEquals(0, count("SELECT count(*) FROM async_jobs WHERE job_type='assessment.analyze'"
                + " AND owner_id IN (SELECT id FROM skin_assessments WHERE gimbal_id=?)",
                gimbal.gimbalId()));
        Map<String, Object> t13 = jdbc.queryForMap(
                "SELECT status, result_summary->>'code' AS code FROM idempotency_requests"
                        + " WHERE principal_type='gimbal' AND principal_id=? AND idempotency_key=?",
                gimbal.gimbalId().toString(), key);
        assertEquals("rejected", t13.get("status"));
        assertEquals("DEVICE_OCCUPIED", t13.get("code"));

        MvcResult replay = postA01(gimbal.token(), key);
        assertEquals(409, replay.getResponse().getStatus());
        assertEquals(error(r), error(replay));
    }

    @Test
    @DisplayName("A01 stopped 未收尾执行 → 409 STOP_NOT_CONFIRMED")
    void stoppedExecution() throws Exception {
        GimbalFixture gimbal = createGimbal();
        seedOpenExecution(gimbal.gimbalId(), "stopped");
        MvcResult r = postA01(gimbal.token(), "d-a01-stopped-" + UUID.randomUUID());
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("STOP_NOT_CONFIRMED", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A01 并发不同键：串行化，2 任务，指针其一，代次 +2")
    void concurrentDifferentKeys() throws Exception {
        GimbalFixture gimbal = createGimbal();
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Callable<MvcResult>> tasks = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            String key = "d-a01-conc-" + i + "-" + UUID.randomUUID();
            tasks.add(() -> {
                start.await();
                return postA01(gimbal.token(), key);
            });
        }
        List<Future<MvcResult>> futures = new ArrayList<>();
        for (Callable<MvcResult> t : tasks) {
            futures.add(pool.submit(t));
        }
        start.countDown();
        List<UUID> ids = new ArrayList<>();
        for (Future<MvcResult> f : futures) {
            MvcResult r = f.get(30, TimeUnit.SECONDS);
            assertEquals(202, r.getResponse().getStatus(), r.getResponse().getContentAsString());
            ids.add(UUID.fromString(data(r).path("taskId").asText()));
        }
        pool.shutdownNow();

        assertNotEquals(ids.get(0), ids.get(1));
        assertEquals(2, count("SELECT count(*) FROM skin_assessments WHERE gimbal_id = ?",
                gimbal.gimbalId()));
        assertEquals(2L, jdbc.queryForObject(
                "SELECT current_assessment_revision FROM gimbals WHERE id = ?", Long.class,
                gimbal.gimbalId()));
        UUID pointer = jdbc.queryForObject(
                "SELECT current_assessment_id FROM gimbals WHERE id = ?", UUID.class,
                gimbal.gimbalId());
        assertTrue(ids.contains(pointer));
    }

    @Test
    @DisplayName("A01 被替换旧任务的键重放：返回原 taskId，指针停留新任务")
    void replayOldReplacedRequest() throws Exception {
        GimbalFixture gimbal = createGimbal();
        String keyA = "d-a01-old-a-" + UUID.randomUUID();
        UUID taskA = acceptA01(gimbal, keyA);
        UUID taskB = acceptA01(gimbal);

        MvcResult replay = postA01(gimbal.token(), keyA);
        assertEquals(200, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        assertEquals(taskA.toString(), data(replay).path("taskId").asText());
        assertTrue(JSON.readTree(replay.getResponse().getContentAsString())
                .path("meta").path("replayed").asBoolean());
        assertEquals(taskB, jdbc.queryForObject(
                "SELECT current_assessment_id FROM gimbals WHERE id = ?", UUID.class,
                gimbal.gimbalId()));
        assertEquals(2L, jdbc.queryForObject(
                "SELECT current_assessment_revision FROM gimbals WHERE id = ?", Long.class,
                gimbal.gimbalId()));
    }

    @Test
    @DisplayName("A01 DEVICE_OCCUPIED 拒绝 → 3 个 media.cleanup；重放不重复；受理成功 0 个")
    void orphanCleanupEnqueuedOnRejection() throws Exception {
        GimbalFixture gimbal = createGimbal();
        seedOpenExecution(gimbal.gimbalId(), "running");
        String key = "d-a01-cleanup-" + UUID.randomUUID();
        MvcResult r = postA01(gimbal.token(), key);
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("DEVICE_OCCUPIED", error(r).path("code").asText());

        UUID t13 = t13IdForGimbalKey(gimbal.gimbalId(), key);
        List<Map<String, Object>> media = jdbc.queryForList(
                "SELECT id::text AS id FROM media_objects WHERE request_id=?", t13);
        assertEquals(3, media.size(), "three ingested media rows expected before rejection");
        assertEquals(3, cleanupJobCountForGimbalKey(gimbal.gimbalId(), key));

        List<Map<String, Object>> jobs = jdbc.queryForList(
                "SELECT job_type, owner_type, owner_id::text AS owner_id, input_revision, dedup_key,"
                        + " payload->>'media_object_id' AS mid, payload->>'cleanup_revision' AS cr,"
                        + " payload->>'schema_version' AS sv,"
                        + " jsonb_typeof(payload->'schema_version') AS svtype"
                        + " FROM async_jobs WHERE job_type='media.cleanup' AND owner_id IN"
                        + " (SELECT id FROM media_objects WHERE request_id=?)", t13);
        assertEquals(3, jobs.size());
        for (Map<String, Object> job : jobs) {
            String ownerId = (String) job.get("owner_id");
            assertEquals("media.cleanup", job.get("job_type"));
            assertEquals("media", job.get("owner_type"));
            assertEquals(1L, ((Number) job.get("input_revision")).longValue());
            assertEquals("media:" + ownerId + ":cleanup:1", job.get("dedup_key"));
            assertEquals(ownerId, job.get("mid"));
            assertEquals("1", job.get("cr"));
            assertEquals("number", job.get("svtype"), "payload schema_version must be a JSON integer");
            assertEquals("1", job.get("sv"));
        }

        MvcResult replay = postA01(gimbal.token(), key);
        assertEquals(409, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        assertEquals(3, cleanupJobCountForGimbalKey(gimbal.gimbalId(), key),
                "replay must not duplicate cleanup jobs (dedup)");
    }

    @Test
    @DisplayName("A01 受理成功 → 全部图片已接纳，0 个 media.cleanup")
    void acceptedHasNoCleanupJobs() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        assertEquals(3, count("SELECT count(*) FROM media_objects WHERE assessment_id=?", taskId));
        assertEquals(0, count("SELECT count(*) FROM async_jobs WHERE job_type='media.cleanup'"
                + " AND owner_id IN (SELECT id FROM media_objects WHERE assessment_id=?)", taskId));
    }

    private int count(String sql, Object... args) {
        return jdbc.queryForObject(sql, Integer.class, args);
    }
}

package cn.yuanxin.mvp.web.assessments;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** M3-A02 补拍（真实 PG）：版本合并、失败列清除、版本/占用/越权拒绝、重放。 */
class AssessmentRetakeIT extends AssessmentTestSupport {

    private static String retakeMetadata(long expected, String... views) {
        StringBuilder sb = new StringBuilder("{\"expectedPhotoVersion\":\"").append(expected)
                .append("\",\"replacedViews\":[");
        for (int i = 0; i < views.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append('"').append(views[i]).append('"');
        }
        return sb.append("]}").toString();
    }

    private Map<String, String> imagesAt(UUID taskId, long version) throws Exception {
        String pv = jdbc.queryForObject(
                "SELECT photo_versions::text FROM skin_assessments WHERE id = ?", String.class, taskId);
        Map<String, String> out = new LinkedHashMap<>();
        for (JsonNode v : JSON.readTree(pv).path("versions")) {
            if (v.path("version").asLong(-1) == version) {
                v.path("images").fields().forEachRemaining(e -> out.put(e.getKey(), e.getValue().asText()));
            }
        }
        return out;
    }

    @Test
    @DisplayName("A02 happy：版本 2 合并（front/right 复用，left 新），代次/任务/失败列更新")
    void happyRetake() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        Map<String, String> original = imagesAt(taskId, 1);
        updateNeedsRetake(taskId, "QUALITY_REJECTED",
                "{\"retryable\":false,\"required_views\":[\"left\"]}");

        String key = "d-a02-happy-" + UUID.randomUUID();
        MvcResult r = putA02(gimbal.token(), key, taskId, 2, retakeMetadata(1, "left"),
                Map.of("left", png(7)));
        assertEquals(202, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertEquals(taskId.toString(), d.path("taskId").asText());
        assertEquals("queued", d.path("status").asText());
        assertEquals("2", d.path("photoVersion").asText());

        Map<String, Object> t05 = jdbc.queryForMap(
                "SELECT status, current_photo_version, processing_revision, failure_code,"
                        + " failure_detail::text AS fd FROM skin_assessments WHERE id = ?", taskId);
        assertEquals("queued", t05.get("status"));
        assertEquals(2L, ((Number) t05.get("current_photo_version")).longValue());
        assertEquals(2L, ((Number) t05.get("processing_revision")).longValue());
        assertNull(t05.get("failure_code"));
        assertNull(t05.get("fd"));

        Map<String, String> merged = imagesAt(taskId, 2);
        assertEquals(original.get("front"), merged.get("front"));
        assertEquals(original.get("right"), merged.get("right"));
        assertNotEquals(original.get("left"), merged.get("left"));

        Map<String, Object> newLeft = jdbc.queryForMap(
                "SELECT photo_version FROM media_objects WHERE id = ?::uuid", merged.get("left"));
        assertEquals(2L, ((Number) newLeft.get("photo_version")).longValue());
        assertEquals(1L, jdbc.queryForObject(
                "SELECT photo_version FROM media_objects WHERE id = ?::uuid", Long.class,
                original.get("left")));

        Map<String, Object> job = jdbc.queryForMap(
                "SELECT input_revision, dedup_key FROM async_jobs WHERE owner_id = ?"
                        + " AND dedup_key = ?", taskId, "assessment:" + taskId + ":2");
        assertEquals(2L, ((Number) job.get("input_revision")).longValue());
    }

    @Test
    @DisplayName("A02 同键同内容重放：200，不增版本/代次")
    void replayNoIncrement() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        updateNeedsRetake(taskId, "QUALITY_REJECTED", "{\"required_views\":[\"left\"]}");
        String key = "d-a02-replay-" + UUID.randomUUID();
        String meta = retakeMetadata(1, "left");
        MvcResult first = putA02(gimbal.token(), key, taskId, 2, meta, Map.of("left", png(7)));
        assertEquals(202, first.getResponse().getStatus(), first.getResponse().getContentAsString());

        MvcResult replay = putA02(gimbal.token(), key, taskId, 2, meta, Map.of("left", png(7)));
        assertEquals(200, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        assertTrue(JSON.readTree(replay.getResponse().getContentAsString())
                .path("meta").path("replayed").asBoolean());
        assertEquals("2", data(replay).path("photoVersion").asText());
        assertEquals(2L, jdbc.queryForObject(
                "SELECT current_photo_version FROM skin_assessments WHERE id = ?", Long.class, taskId));
        assertEquals(2L, jdbc.queryForObject(
                "SELECT processing_revision FROM skin_assessments WHERE id = ?", Long.class, taskId));
    }

    @Test
    @DisplayName("A02 期望版本不符 / 路径跳版 → 409 PHOTO_VERSION_CONFLICT")
    void versionConflicts() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID wrongExpected = acceptA01(gimbal);
        updateNeedsRetake(wrongExpected, "QUALITY_REJECTED", "{\"required_views\":[\"left\"]}");
        MvcResult r1 = putA02(gimbal.token(), "d-a02-" + UUID.randomUUID(), wrongExpected, 2,
                retakeMetadata(0, "left"), Map.of("left", png(7)));
        assertEquals(409, r1.getResponse().getStatus(), r1.getResponse().getContentAsString());
        assertEquals("PHOTO_VERSION_CONFLICT", error(r1).path("code").asText());

        UUID jump = acceptA01(gimbal);
        updateNeedsRetake(jump, "QUALITY_REJECTED", "{\"required_views\":[\"left\"]}");
        MvcResult r2 = putA02(gimbal.token(), "d-a02-" + UUID.randomUUID(), jump, 3,
                retakeMetadata(1, "left"), Map.of("left", png(7)));
        assertEquals(409, r2.getResponse().getStatus(), r2.getResponse().getContentAsString());
        assertEquals("PHOTO_VERSION_CONFLICT", error(r2).path("code").asText());
    }

    @Test
    @DisplayName("A02 report_ready 任务补拍 → 409 PHOTO_VERSION_CONFLICT")
    void reportReadyConflict() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID memberId = seedMember();
        UUID taskId = acceptA01(gimbal);
        markReportReady(taskId, memberId);
        MvcResult r = putA02(gimbal.token(), "d-a02-" + UUID.randomUUID(), taskId, 2,
                retakeMetadata(1, "left"), Map.of("left", png(7)));
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("PHOTO_VERSION_CONFLICT", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A02 被替换任务 → 409 TASK_REPLACED；未接纳图片入队 1 个 media.cleanup")
    void replacedTask() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskA = acceptA01(gimbal);
        updateNeedsRetake(taskA, "QUALITY_REJECTED", "{\"required_views\":[\"left\"]}");
        acceptA01(gimbal);
        String key = "d-a02-" + UUID.randomUUID();
        MvcResult r = putA02(gimbal.token(), key, taskA, 2,
                retakeMetadata(1, "left"), Map.of("left", png(7)));
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("TASK_REPLACED", error(r).path("code").asText());
        assertEquals(1, cleanupJobCountForGimbalKey(gimbal.gimbalId(), key));
    }

    @Test
    @DisplayName("A02 他人云台任务 / 随机 taskId → 404；APP → 403")
    void authorization() throws Exception {
        GimbalFixture owner = createGimbal();
        GimbalFixture other = createGimbal();
        UUID taskId = acceptA01(owner);
        updateNeedsRetake(taskId, "QUALITY_REJECTED", "{\"required_views\":[\"left\"]}");

        MvcResult foreign = putA02(other.token(), "d-a02-" + UUID.randomUUID(), taskId, 2,
                retakeMetadata(1, "left"), Map.of("left", png(7)));
        assertEquals(404, foreign.getResponse().getStatus(), foreign.getResponse().getContentAsString());
        assertEquals("RESOURCE_NOT_VISIBLE", error(foreign).path("code").asText());

        MvcResult random = putA02(owner.token(), "d-a02-" + UUID.randomUUID(), UUID.randomUUID(), 2,
                retakeMetadata(1, "left"), Map.of("left", png(7)));
        assertEquals(404, random.getResponse().getStatus(), random.getResponse().getContentAsString());

        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a02-app");
        MvcResult appResult = putA02(app.accessToken(), "d-a02-" + UUID.randomUUID(), taskId, 2,
                retakeMetadata(1, "left"), Map.of("left", png(7)));
        assertEquals(403, appResult.getResponse().getStatus(), appResult.getResponse().getContentAsString());
        assertEquals("CALLER_NOT_ALLOWED", error(appResult).path("code").asText());
    }

    @Test
    @DisplayName("A02 更换清单与图片 part 不匹配（多 part / 缺 part）→ 400")
    void partMismatch() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID extra = acceptA01(gimbal);
        updateNeedsRetake(extra, "QUALITY_REJECTED", "{\"required_views\":[\"left\"]}");
        MvcResult r1 = putA02(gimbal.token(), "d-a02-" + UUID.randomUUID(), extra, 2,
                retakeMetadata(1, "left"), Map.of("left", png(7), "front", png(8)));
        assertEquals(400, r1.getResponse().getStatus(), r1.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(r1).path("code").asText());

        UUID missing = acceptA01(gimbal);
        updateNeedsRetake(missing, "QUALITY_REJECTED", "{\"required_views\":[\"left\"]}");
        MvcResult r2 = putA02(gimbal.token(), "d-a02-" + UUID.randomUUID(), missing, 2,
                retakeMetadata(1, "left"), Map.of());
        assertEquals(400, r2.getResponse().getStatus(), r2.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(r2).path("code").asText());
    }

    @Test
    @DisplayName("A02 补拍 metadata.expectedPhotoVersion 非法 bigint → 400 INVALID_INPUT")
    void malformedExpectedVersion() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        for (String bad : new String[]{"01", "abc", "-1", "1.0"}) {
            MvcResult r = putA02(gimbal.token(), "d-a02-" + UUID.randomUUID(), taskId, 2,
                    "{\"expectedPhotoVersion\":\"" + bad + "\",\"replacedViews\":[\"left\"]}",
                    Map.of("left", png(7)));
            assertEquals(400, r.getResponse().getStatus(),
                    "expected 400 for expectedPhotoVersion=" + bad + ": "
                            + r.getResponse().getContentAsString());
            assertEquals("INVALID_INPUT", error(r).path("code").asText());
        }
        // 解析失败在任何 begin/ingest 之前：不产生版本变化
        assertEquals(1L, jdbc.queryForObject(
                "SELECT current_photo_version FROM skin_assessments WHERE id = ?", Long.class, taskId));
    }

    @Test
    @DisplayName("A02 既有版本缺少视角 → 500 INTERNAL，整事务回滚，不追加残缺版本")
    void incompletePriorViewSetRollsBack() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        String partial = "{\"schema_version\":1,\"versions\":[{\"version\":1,\"images\":{"
                + "\"left\":\"" + UUID.randomUUID() + "\",\"right\":\"" + UUID.randomUUID()
                + "\"},\"quality\":{\"status\":\"pending\",\"required_views\":[]}}]}";
        jdbc.update("UPDATE skin_assessments SET status='needs_retake', photo_versions=?::jsonb"
                + " WHERE id=?", partial, taskId);

        String key = "d-a02-partial-" + UUID.randomUUID();
        MvcResult r = putA02(gimbal.token(), key, taskId, 2, retakeMetadata(1, "left"),
                Map.of("left", png(7)));
        assertEquals(500, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("INTERNAL", error(r).path("code").asText());

        Map<String, Object> t05 = jdbc.queryForMap(
                "SELECT status, current_photo_version FROM skin_assessments WHERE id = ?", taskId);
        assertEquals("needs_retake", t05.get("status"));
        assertEquals(1L, ((Number) t05.get("current_photo_version")).longValue());
        assertEquals(1, count("SELECT jsonb_array_length(photo_versions->'versions')"
                + " FROM skin_assessments WHERE id = ?", taskId));
        String t13Status = jdbc.queryForObject(
                "SELECT status FROM idempotency_requests WHERE principal_type='gimbal'"
                        + " AND principal_id=? AND idempotency_key=?",
                String.class, gimbal.gimbalId().toString(), key);
        assertNotEquals("succeeded", t13Status);
        // 仅有 A01 的初始分析任务；补拍事务回滚不得留下 revision=2 的新任务
        assertEquals(0, count("SELECT count(*) FROM async_jobs WHERE dedup_key=?",
                "assessment:" + taskId + ":2"));
        // 业务事务异常回滚路径 (b)：未接纳的 left 图片入队 1 个 media.cleanup
        assertEquals(1, cleanupJobCountForGimbalKey(gimbal.gimbalId(), key));
    }

    private int count(String sql, Object... args) {
        return jdbc.queryForObject(sql, Integer.class, args);
    }
}

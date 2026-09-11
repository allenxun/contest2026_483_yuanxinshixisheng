package cn.yuanxin.mvp.web.assessments;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.sql.Timestamp;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/** M3-A03 任务查询 / M3-A06 云台当前任务（真实 PG）：鉴权统一 404、失败有界投影、无写。 */
class AssessmentQueryIT extends AssessmentTestSupport {

    private MvcResult getTask(String token, UUID taskId) throws Exception {
        return mockMvc.perform(get("/api/v1/skin-assessment-tasks/" + taskId)
                        .header("Authorization", "Bearer " + token))
                .andReturn();
    }

    private MvcResult getCurrent(String token, UUID gimbalId) throws Exception {
        return mockMvc.perform(get("/api/v1/gimbals/" + gimbalId + "/current-assessment")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
    }

    @Test
    @DisplayName("A03 云台当前任务 → 200 全字段 + no-store + 零写")
    void gimbalCurrentTask() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        Timestamp before = jdbc.queryForObject(
                "SELECT updated_at FROM skin_assessments WHERE id = ?", Timestamp.class, taskId);

        MvcResult r = getTask(gimbal.token(), taskId);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        JsonNode d = data(r);
        assertEquals(taskId.toString(), d.path("taskId").asText());
        assertEquals("queued", d.path("status").asText());
        assertEquals("1", d.path("photoVersion").asText());
        assertTrue(d.path("requiredViews").isArray());
        assertEquals(0, d.path("requiredViews").size());
        assertTrue(d.path("failureCode").isNull());
        assertTrue(d.path("retryable").isNull());
        assertTrue(d.path("reportId").isNull());
        assertTrue(d.path("planAvailability").isNull());

        Timestamp after = jdbc.queryForObject(
                "SELECT updated_at FROM skin_assessments WHERE id = ?", Timestamp.class, taskId);
        assertEquals(before, after);
    }

    @Test
    @DisplayName("A03 被替换任务 → 409 TASK_REPLACED")
    void gimbalReplaced() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskA = acceptA01(gimbal);
        acceptA01(gimbal);
        MvcResult r = getTask(gimbal.token(), taskA);
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("TASK_REPLACED", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A03 他人云台 / 随机 taskId → 404 RESOURCE_NOT_VISIBLE")
    void gimbalNotVisible() throws Exception {
        GimbalFixture owner = createGimbal();
        GimbalFixture other = createGimbal();
        UUID taskId = acceptA01(owner);
        MvcResult foreign = getTask(other.token(), taskId);
        MvcResult random = getTask(other.token(), UUID.randomUUID());
        assertEquals(404, foreign.getResponse().getStatus());
        assertEquals(404, random.getResponse().getStatus());
        assertEquals(error(foreign), error(random));

        MvcResult randomOwner = getTask(owner.token(), UUID.randomUUID());
        assertEquals(404, randomOwner.getResponse().getStatus());
    }

    @Test
    @DisplayName("A03 APP 有 active 授权 + member_id → 200；撤销 / member_id NULL → 404")
    void appGrant() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID memberId = seedMember();
        UUID taskId = acceptA01(gimbal);
        setMember(taskId, memberId);

        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a03-app");
        seedGrant(app.accountId(), memberId, "active");
        MvcResult ok = getTask(app.accessToken(), taskId);
        assertEquals(200, ok.getResponse().getStatus(), ok.getResponse().getContentAsString());

        UUID revokedTask = acceptA01(gimbal);
        UUID revokedMember = seedMember();
        setMember(revokedTask, revokedMember);
        seedGrant(app.accountId(), revokedMember, "revoked");
        MvcResult revoked = getTask(app.accessToken(), revokedTask);
        assertEquals(404, revoked.getResponse().getStatus(), revoked.getResponse().getContentAsString());

        UUID nullMemberTask = acceptA01(gimbal);
        MvcResult nullMember = getTask(app.accessToken(), nullMemberTask);
        assertEquals(404, nullMember.getResponse().getStatus());
    }

    @Test
    @DisplayName("A03 失败投影（封闭映射）：failureCode 公开、retryable=false、failure_detail 不泄露")
    void failureProjectionClosedMapping() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        String longText = "x".repeat(4096);
        jdbc.update("UPDATE skin_assessments SET status='failed', failure_code=?,"
                        + " failure_detail=?::jsonb WHERE id=?",
                "QUALITY_REJECTED",
                "{\"retryable\":true,\"marker\":\"SECRET_MARKER\",\"diagnostic\":\"" + longText + "\"}",
                taskId);

        MvcResult r = getTask(gimbal.token(), taskId);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertEquals("QUALITY_REJECTED", d.path("failureCode").asText());
        assertFalse(d.path("retryable").asBoolean(),
                "closed mapping must ignore failure_detail retryable=true");
        assertFalse(d.has("failureDetail"));
        String raw = r.getResponse().getContentAsString();
        assertFalse(raw.contains("SECRET_MARKER"), raw);
        assertFalse(raw.contains(longText), "long failure detail must not be echoed");
        assertFalse(raw.contains("diagnostic"), raw);
        assertEquals(0, d.path("requiredViews").size());
    }

    @Test
    @DisplayName("A03 failureCode 封闭白名单：未知/内部码 failed+needs_retake 均投影 null 且不外泄")
    void failureCodeClosedWhitelist() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID failed = acceptA01(gimbal);
        updateTaskFields(failed, "failed", "INTERNAL_SECRET_X",
                "{\"marker\":\"INTERNAL_SECRET_X\"}", null);
        MvcResult failedResult = getTask(gimbal.token(), failed);
        assertEquals(200, failedResult.getResponse().getStatus(),
                failedResult.getResponse().getContentAsString());
        assertTrue(data(failedResult).path("failureCode").isNull(),
                "unknown failure_code must project to null");
        assertFalse(failedResult.getResponse().getContentAsString().contains("INTERNAL_SECRET_X"),
                failedResult.getResponse().getContentAsString());

        UUID retake = acceptA01(gimbal);
        updateTaskFields(retake, "needs_retake", "INTERNAL_SECRET_X", null,
                "{\"schema_version\":1,\"quality\":{\"status\":\"needs_retake\","
                        + "\"required_views\":[\"left\"]}}");
        MvcResult retakeResult = getTask(gimbal.token(), retake);
        assertEquals(200, retakeResult.getResponse().getStatus(),
                retakeResult.getResponse().getContentAsString());
        assertTrue(data(retakeResult).path("failureCode").isNull(),
                "unknown failure_code must project to null on needs_retake");
        assertFalse(retakeResult.getResponse().getContentAsString().contains("INTERNAL_SECRET_X"),
                retakeResult.getResponse().getContentAsString());
    }

    @Test
    @DisplayName("A03 failureCode 白名单内码全部原样投影且 retryable=false")
    void failureCodeWhitelistProjected() throws Exception {
        GimbalFixture gimbal = createGimbal();
        String[] codes = {
                "QUALITY_REJECTED",
                "NOT_SAME_PERSON",
                "IDENTITY_UNCERTAIN",
                "IDENTITY_ENROLLMENT_TIMEOUT",
                "SOURCE_IMAGE_UNAVAILABLE",
                "RESULT_ARCHIVE_FAILED",
                "PROVIDER_CONTRACT_VIOLATION",
                "MEMBER_NOT_VISIBLE",
                "DEPENDENCY_UNAVAILABLE"};
        for (String code : codes) {
            UUID taskId = acceptA01(gimbal);
            updateTaskFields(taskId, "failed", code, null, null);
            MvcResult r = getTask(gimbal.token(), taskId);
            assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
            assertEquals(code, data(r).path("failureCode").asText(),
                    "whitelisted code must project verbatim: " + code);
            assertFalse(data(r).path("retryable").asBoolean());
        }
    }

    @Test
    @DisplayName("A03 requiredViews 来自 identity_result.quality.required_views（枚举过滤+去重）")
    void requiredViewsFromIdentityResult() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        updateTaskFields(taskId, "needs_retake", "QUALITY_REJECTED",
                "{\"retryable\":true,\"marker\":\"SECRET_MARKER\"}",
                "{\"schema_version\":1,\"quality\":{\"status\":\"needs_retake\","
                        + "\"required_views\":[\"left\",\"junk\",\"left\",\"right\"]}}");
        MvcResult r = getTask(gimbal.token(), taskId);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertFalse(d.path("retryable").asBoolean());
        List<String> views = new java.util.ArrayList<>();
        d.path("requiredViews").forEach(n -> views.add(n.asText()));
        assertEquals(List.of("left", "right"), views);
        assertFalse(r.getResponse().getContentAsString().contains("SECRET_MARKER"));
    }

    @Test
    @DisplayName("A03 非 needs_retake 状态 → requiredViews 空；null failure_code → retryable null")
    void requiredViewsEmptyOutsideNeedsRetake() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID taskId = acceptA01(gimbal);
        updateTaskFields(taskId, "queued", null, null,
                "{\"schema_version\":1,\"quality\":{\"status\":\"needs_retake\","
                        + "\"required_views\":[\"left\"]}}");
        MvcResult r = getTask(gimbal.token(), taskId);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertTrue(d.path("retryable").isNull());
        assertTrue(d.path("failureCode").isNull());
        assertEquals(0, d.path("requiredViews").size());
    }

    @Test
    @DisplayName("A03 failed 无诊断列 → retryable=false；损坏 identity_result → requiredViews 空")
    void retryableClosedAndMalformedIdentityResult() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID failed = acceptA01(gimbal);
        jdbc.update("UPDATE skin_assessments SET status='failed', failure_code=? WHERE id=?",
                "NOT_SAME_PERSON", failed);
        MvcResult r1 = getTask(gimbal.token(), failed);
        assertEquals(200, r1.getResponse().getStatus());
        assertEquals("NOT_SAME_PERSON", data(r1).path("failureCode").asText());
        assertFalse(data(r1).path("retryable").asBoolean());

        UUID malformed = acceptA01(gimbal);
        updateTaskFields(malformed, "needs_retake", "QUALITY_REJECTED", null,
                "{\"schema_version\":1,\"quality\":{\"required_views\":\"nope\"}}");
        MvcResult r2 = getTask(gimbal.token(), malformed);
        assertEquals(200, r2.getResponse().getStatus());
        assertEquals(0, data(r2).path("requiredViews").size());
        assertFalse(data(r2).path("retryable").asBoolean());
    }

    @Test
    @DisplayName("A03 planAvailability 反映关联方案生成状态")
    void planAvailability() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID memberId = seedMember();
        UUID taskId = acceptA01(gimbal);
        setMember(taskId, memberId);
        seedCarePlan(taskId, memberId, "waiting_inputs");
        MvcResult r = getTask(gimbal.token(), taskId);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("waiting_inputs", data(r).path("planAvailability").asText());
    }

    @Test
    @DisplayName("A06 自身当前任务 → 200 形状；空指针 → null + 代次")
    void currentAssessment() throws Exception {
        GimbalFixture gimbal = createGimbal();
        MvcResult empty = getCurrent(gimbal.token(), gimbal.gimbalId());
        assertEquals(200, empty.getResponse().getStatus(), empty.getResponse().getContentAsString());
        assertTrue(data(empty).path("currentAssessment").isNull());
        assertEquals("0", data(empty).path("currentAssessmentRevision").asText());

        UUID taskId = acceptA01(gimbal);
        MvcResult r = getCurrent(gimbal.token(), gimbal.gimbalId());
        assertEquals(200, r.getResponse().getStatus());
        JsonNode cur = data(r).path("currentAssessment");
        assertEquals(taskId.toString(), cur.path("taskId").asText());
        assertEquals("queued", cur.path("status").asText());
        assertEquals("1", cur.path("photoVersion").asText());
        assertTrue(cur.path("reportId").isNull());
        assertEquals("1", data(r).path("currentAssessmentRevision").asText());
    }

    @Test
    @DisplayName("A06 他人云台 id / APP → 403；A06 零写")
    void currentAssessmentAuthorizationAndNoWrites() throws Exception {
        GimbalFixture self = createGimbal();
        GimbalFixture other = createGimbal();
        acceptA01(self);
        MvcResult otherResult = getCurrent(other.token(), self.gimbalId());
        assertEquals(403, otherResult.getResponse().getStatus(), otherResult.getResponse().getContentAsString());
        assertEquals("CALLER_NOT_ALLOWED", error(otherResult).path("code").asText());

        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a06-app");
        MvcResult appResult = getCurrent(app.accessToken(), self.gimbalId());
        assertEquals(403, appResult.getResponse().getStatus());
        assertEquals("CALLER_NOT_ALLOWED", error(appResult).path("code").asText());

        Timestamp t03Before = jdbc.queryForObject(
                "SELECT updated_at FROM gimbals WHERE id = ?", Timestamp.class, self.gimbalId());
        MvcResult ok = getCurrent(self.token(), self.gimbalId());
        assertEquals(200, ok.getResponse().getStatus());
        Timestamp t03After = jdbc.queryForObject(
                "SELECT updated_at FROM gimbals WHERE id = ?", Timestamp.class, self.gimbalId());
        assertEquals(t03Before, t03After);
    }
}

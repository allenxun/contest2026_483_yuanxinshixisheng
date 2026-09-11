package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/** M4-A07 执行查询 + M4-A08 进度 + M4-A09 执行历史集成测试（真实 PG）。 */
class CareExecutionQueryIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private MvcResult getExecution(String token, UUID executionId, String query) throws Exception {
        return mockMvc.perform(get("/api/v1/care-executions/" + executionId + query)
                .header("Authorization", "Bearer " + token)).andReturn();
    }

    private MvcResult getProgress(String token, UUID planId, String query) throws Exception {
        return mockMvc.perform(get("/api/v1/care-plans/" + planId + "/progress" + query)
                .header("Authorization", "Bearer " + token)).andReturn();
    }

    private MvcResult getExecutions(String token, UUID memberId, String query) throws Exception {
        return mockMvc.perform(get("/api/v1/members/" + memberId + "/care-executions" + query)
                .header("Authorization", "Bearer " + token)).andReturn();
    }

    private static final String LATEST_OBSERVATION = "{\"schema_version\":1,\"epoch\":\"epoch-1\","
            + "\"seq\":\"2\",\"state\":\"running\",\"occurred_at\":\"2026-09-10T04:00:00Z\","
            + "\"verification_revision\":\"2\",\"continuity_valid\":false}";

    // ---------------- M4-A07 ----------------

    @Test
    @DisplayName("A07 授权 APP 完整视图：controller/member/plan/进度/观测/水位/确认 ID 齐全，bigint 字符串")
    void a07FullViewAuthorizedApp() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a07-full");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a07-full-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 4, 1, 2, null);
        UUID microcrystalId = fx.seedMicrocrystal();
        UUID executionId = fx.seedAppExecution(planId, memberId, microcrystalId,
                fx.seedAssessment(gimbalId, memberId), accountId, "inst-a07-full");
        jdbc.update("UPDATE care_executions SET status='running', verification_revision=2,"
                        + " observation_epoch='epoch-1', last_observation_seq=3,"
                        + " latest_observation=CAST(? AS jsonb), accepted_count=3 WHERE id=?",
                LATEST_OBSERVATION, executionId);
        fx.seedRecord(executionId, planId, memberId, microcrystalId, "r1", "epoch-1", 1, 1);
        fx.seedRecord(executionId, planId, memberId, microcrystalId, "r2", "epoch-1", 2, 1);
        fx.seedRecord(executionId, planId, memberId, microcrystalId, "r3", "epoch-1", 3, 1);

        MvcResult r = getExecution(login.accessToken(), executionId, "?recordsAfterSeq=1&limit=10");
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        JsonNode d = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals(executionId.toString(), d.path("executionId").asText());
        assertEquals("running", d.path("status").asText());
        assertEquals("app_account", d.path("controller").path("controllerType").asText());
        assertEquals("inst-a07-full", d.path("controller").path("installationId").asText());
        assertTrue(d.path("controller").path("gimbalId").isNull());
        assertEquals(memberId.toString(), d.path("memberId").asText());
        assertEquals(planId.toString(), d.path("planId").asText());
        assertEquals(microcrystalId.toString(), d.path("microcrystalId").asText());
        assertTrue(d.path("acceptedCount").isTextual());
        assertEquals("3", d.path("acceptedCount").asText());
        assertTrue(d.path("closedAt").isNull());

        JsonNode obs = d.path("latestObservation");
        assertEquals("epoch-1", obs.path("epoch").asText());
        assertEquals("2", obs.path("seq").asText());
        assertEquals("running", obs.path("state").asText());
        assertEquals("2026-09-10T04:00:00Z", obs.path("occurredAt").asText());
        assertEquals("2", obs.path("verificationRevision").asText());
        assertFalse(obs.path("continuityValid").asBoolean(true));

        JsonNode wm = d.path("recordWatermark");
        assertEquals("epoch-1", wm.path("epoch").asText());
        assertEquals("3", wm.path("maxSourceSeq").asText());
        assertEquals("3", wm.path("acceptedCount").asText());
        assertTrue(wm.path("maxSourceSeq").isTextual());

        JsonNode ids = d.path("acknowledgedRecordIds");
        assertEquals(2, ids.size());
        assertEquals("r2", ids.get(0).asText());
        assertEquals("r3", ids.get(1).asText());

        JsonNode progress = d.path("progress");
        assertEquals("4", progress.path("targetCount").asText());
        assertEquals("1", progress.path("completedCount").asText());
        assertEquals("3", progress.path("remainingCount").asText());
    }

    @Test
    @DisplayName("A07 撤销授权后原控制端 APP → 最小对账视图；T07 行只读不变")
    void a07OriginalControllerMinimalAfterRevoke() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a07-min");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a07-min-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 4, 1, 2, null);
        UUID microcrystalId = fx.seedMicrocrystal();
        UUID executionId = fx.seedAppExecution(planId, memberId, microcrystalId,
                fx.seedAssessment(gimbalId, memberId), accountId, "inst-a07-min");
        jdbc.update("UPDATE care_executions SET observation_epoch='epoch-1', accepted_count=3 WHERE id=?",
                executionId);
        fx.revokeGrant(accountId, memberId);

        Map<String, Object> before = readExecutionState(executionId);
        MvcResult r = getExecution(login.accessToken(), executionId, "?recordsAfterSeq=0");
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals(executionId.toString(), d.path("executionId").asText());
        assertEquals("admitted", d.path("status").asText());
        assertEquals("3", d.path("acceptedCount").asText());
        assertTrue(d.path("recordWatermark").path("maxSourceSeq").isTextual());
        assertTrue(d.path("acknowledgedRecordIds").isArray());
        assertTrue(d.path("controller").isNull());
        assertTrue(d.path("memberId").isNull());
        assertTrue(d.path("planId").isNull());
        assertTrue(d.path("microcrystalId").isNull());
        assertTrue(d.path("latestObservation").isNull());
        assertTrue(d.path("progress").isNull());
        assertEquals(before, readExecutionState(executionId));
    }

    @Test
    @DisplayName("A07 云台原控制端 → 最小视图；无关账号与不存在 404 全等；非法 recordsAfterSeq 400")
    void a07GimbalMinimalAndErrors() throws Exception {
        // 云台原控制端
        UUID gimbalId = fx.seedGimbal("a07-gimbal-login-" + UUID.randomUUID(), 1);
        String gimbalToken = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID gimbalAssessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(gimbalAssessment, memberId, 3, 0, 0, null);
        UUID microcrystalId = fx.seedMicrocrystal();
        UUID executionId = fx.seedGimbalExecution(planId, memberId, microcrystalId,
                gimbalAssessment, gimbalId);
        jdbc.update("UPDATE care_executions SET observation_epoch='epoch-g', accepted_count=1 WHERE id=?",
                executionId);

        MvcResult r = getExecution(gimbalToken, executionId, "");
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals(executionId.toString(), d.path("executionId").asText());
        assertTrue(d.path("controller").isNull());
        assertTrue(d.path("memberId").isNull());
        assertTrue(d.path("progress").isNull());
        assertEquals("1", d.path("acceptedCount").asText());

        // 无关账号 404 与不存在 404 全等
        LoginResult unrelated = loginAppWithInstallation(newPhone(), "inst-a07-unrelated");
        MvcResult other = getExecution(unrelated.accessToken(), executionId, "");
        assertEquals(404, other.getResponse().getStatus());
        MvcResult missing = getExecution(unrelated.accessToken(), UUID.randomUUID(), "");
        assertEquals(404, missing.getResponse().getStatus());
        assertEquals(CareTestFixtures.errorTree(other), CareTestFixtures.errorTree(missing));

        // 非法 recordsAfterSeq
        assertEquals(400, getExecution(gimbalToken, executionId, "?recordsAfterSeq=01")
                .getResponse().getStatus());
        assertEquals(400, getExecution(gimbalToken, executionId,
                "?recordsAfterSeq=999999999999999999999999999999").getResponse().getStatus());
        assertEquals(400, getExecution(gimbalToken, executionId, "?recordsAfterSeq=abc")
                .getResponse().getStatus());
    }

    private Map<String, Object> readExecutionState(UUID executionId) {
        return jdbc.queryForMap("SELECT status, accepted_count, observation_epoch,"
                + " last_observation_seq, verification_revision, latest_observation::text, closed_at"
                + " FROM care_executions WHERE id=?", executionId);
    }

    // ---------------- M4-A08 ----------------

    @Test
    @DisplayName("A08 APP：N=10/K=3→remaining 7 未完成；K=10→完成；rev=0→lastSyncedAt null；非 ready 409")
    void a08AppProgress() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a08-app");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a08-app-g-" + UUID.randomUUID(), 1);

        UUID partial = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 10, 3, 1,
                Instant.parse("2026-09-10T04:00:00Z"));
        MvcResult p = getProgress(login.accessToken(), partial, "");
        assertEquals(200, p.getResponse().getStatus(), p.getResponse().getContentAsString());
        assertEquals("no-store", p.getResponse().getHeader("Cache-Control"));
        JsonNode pd = JSON.readTree(p.getResponse().getContentAsString()).path("data");
        assertEquals("10", pd.path("targetCount").asText());
        assertEquals("3", pd.path("completedCount").asText());
        assertEquals("7", pd.path("remainingCount").asText());
        assertFalse(pd.path("isCompleted").asBoolean(true));
        assertFalse(pd.path("lastSyncedAt").isNull());

        UUID complete = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 10, 10, 2, null);
        JsonNode cd = JSON.readTree(getProgress(login.accessToken(), complete, "")
                .getResponse().getContentAsString()).path("data");
        assertEquals("0", cd.path("remainingCount").asText());
        assertTrue(cd.path("isCompleted").asBoolean());

        UUID fresh = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        JsonNode fd = JSON.readTree(getProgress(login.accessToken(), fresh, "")
                .getResponse().getContentAsString()).path("data");
        assertTrue(fd.path("lastSyncedAt").isNull());

        UUID waiting = fx.seedWaitingPlan(fx.seedAssessment(gimbalId, memberId), memberId, "{}");
        MvcResult notReady = getProgress(login.accessToken(), waiting, "");
        assertEquals(409, notReady.getResponse().getStatus());
        assertEquals("PLAN_NOT_READY",
                JSON.readTree(notReady.getResponse().getContentAsString()).path("error").path("code").asText());

        fx.revokeGrant(accountId, memberId);
        assertEquals(404, getProgress(login.accessToken(), fresh, "").getResponse().getStatus());
    }

    @Test
    @DisplayName("A08 云台：合法上下文 200；缺参 400；过期核验/方案不符 404；指针已换 409 TASK_REPLACED")
    void a08GimbalPath() throws Exception {
        UUID gimbalId = fx.seedGimbal("a08-gimbal-login-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 8, 2, 1, null);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID microcrystalId = fx.seedMicrocrystal();
        UUID executionId = fx.seedGimbalExecution(planId, memberId, microcrystalId, assessment, gimbalId);
        jdbc.update("UPDATE care_executions SET verification_revision=5 WHERE id=?", executionId);

        MvcResult ok = getProgress(token, planId,
                "?executionId=" + executionId + "&verificationRevision=5");
        assertEquals(200, ok.getResponse().getStatus(), ok.getResponse().getContentAsString());
        JsonNode d = JSON.readTree(ok.getResponse().getContentAsString()).path("data");
        assertEquals("8", d.path("targetCount").asText());
        assertEquals("2", d.path("completedCount").asText());
        assertEquals("6", d.path("remainingCount").asText());

        // 缺参
        assertEquals(400, getProgress(token, planId, "?executionId=" + executionId).getResponse().getStatus());
        assertEquals(400, getProgress(token, planId, "?verificationRevision=5").getResponse().getStatus());

        // 过期核验
        MvcResult stale = getProgress(token, planId,
                "?executionId=" + executionId + "&verificationRevision=4");
        assertEquals(404, stale.getResponse().getStatus());
        assertEquals("RESOURCE_NOT_VISIBLE",
                JSON.readTree(stale.getResponse().getContentAsString()).path("error").path("code").asText());

        // 方案不符
        UUID otherAssessment = fx.seedAssessment(gimbalId, memberId);
        UUID otherPlan = fx.seedReadyPlan(otherAssessment, memberId, 3, 0, 0, null);
        MvcResult mismatch = getProgress(token, otherPlan,
                "?executionId=" + executionId + "&verificationRevision=5");
        assertEquals(404, mismatch.getResponse().getStatus());

        // T03 指针已换（指向另一评估）→ 409 TASK_REPLACED
        fx.pointGimbalAtAssessment(gimbalId, otherAssessment);
        MvcResult replaced = getProgress(token, planId,
                "?executionId=" + executionId + "&verificationRevision=5");
        assertEquals(409, replaced.getResponse().getStatus());
        assertEquals("TASK_REPLACED",
                JSON.readTree(replaced.getResponse().getContentAsString()).path("error").path("code").asText());
    }

    // ---------------- M4-A09 ----------------

    @Test
    @DisplayName("A09 列表：冻结快照摘要、planId/from/to 过滤、翻页；改 T06 不影响快照；撤销 404、云台 403")
    void a09ListFilterAndSnapshotFreeze() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a09");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a09-g-" + UUID.randomUUID(), 1);
        Instant base = Instant.now().minusSeconds(600);

        UUID planA = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 1, 1, null);
        UUID planB = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 1, 1, null);
        UUID planC = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 1, 1, null);
        UUID execA = fx.execution(planA, memberId, fx.seedMicrocrystal(), fx.seedAssessment(gimbalId, memberId))
                .controllerApp(accountId, "inst-a09").status("closed")
                .planSnapshot("{\"schema_version\":1,\"summary\":{\"title\":\"快照A\"}}")
                .createdAt(base).closedAt(base.plusSeconds(10)).acceptedCount(1).insert();
        UUID execB = fx.execution(planB, memberId, fx.seedMicrocrystal(), fx.seedAssessment(gimbalId, memberId))
                .controllerApp(accountId, "inst-a09")
                .planSnapshot("{\"schema_version\":1,\"summary\":{\"title\":\"快照B\"}}")
                .createdAt(base.plusSeconds(100)).acceptedCount(2).insert();
        UUID execC = fx.execution(planC, memberId, fx.seedMicrocrystal(), fx.seedAssessment(gimbalId, memberId))
                .controllerApp(accountId, "inst-a09")
                .planSnapshot("{\"schema_version\":1,\"summary\":{\"title\":\"快照C\"}}")
                .createdAt(base.plusSeconds(200)).acceptedCount(3).insert();

        // 改 T06 当前值，不应影响 T07 冻结快照
        jdbc.update("UPDATE care_plans SET plan_summary=CAST('{\"schema_version\":1,\"title\":\"改了\"}' AS jsonb)"
                + " WHERE id=?", planC);

        MvcResult r = getExecutions(login.accessToken(), memberId, "?limit=2");
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        JsonNode d = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals(2, d.path("items").size());
        // created_at DESC：C, B
        assertEquals(execC.toString(), d.path("items").get(0).path("executionId").asText());
        assertEquals("快照C", d.path("items").get(0).path("planSnapshotSummary").path("title").asText());
        assertEquals(execB.toString(), d.path("items").get(1).path("executionId").asText());
        assertEquals("admitted", d.path("items").get(0).path("status").asText());
        assertTrue(d.path("items").get(0).path("acceptedCount").isTextual());
        assertFalse(d.path("nextCursor").isNull());
        String cursor = d.path("nextCursor").asText();
        // 续页只有 A
        JsonNode d2 = JSON.readTree(getExecutions(login.accessToken(), memberId,
                "?limit=2&cursor=" + cursor).getResponse().getContentAsString()).path("data");
        assertEquals(1, d2.path("items").size());
        assertEquals(execA.toString(), d2.path("items").get(0).path("executionId").asText());
        assertEquals("closed", d2.path("items").get(0).path("status").asText());

        // planId 过滤
        JsonNode byPlan = JSON.readTree(getExecutions(login.accessToken(), memberId,
                "?planId=" + planB).getResponse().getContentAsString()).path("data");
        assertEquals(1, byPlan.path("items").size());
        assertEquals(execB.toString(), byPlan.path("items").get(0).path("executionId").asText());

        // from/to 过滤（含 B, C，不含 A）
        String from = base.plusSeconds(50).toString();
        String to = base.plusSeconds(500).toString();
        JsonNode byTime = JSON.readTree(getExecutions(login.accessToken(), memberId,
                "?from=" + from + "&to=" + to).getResponse().getContentAsString()).path("data");
        assertEquals(2, byTime.path("items").size());

        // 非法 from 400
        assertEquals(400, getExecutions(login.accessToken(), memberId, "?from=not-a-time")
                .getResponse().getStatus());

        // 撤销 → 404
        fx.revokeGrant(accountId, memberId);
        assertEquals(404, getExecutions(login.accessToken(), memberId, "").getResponse().getStatus());

        // 云台 → 403
        UUID gimbal2 = fx.seedGimbal("a09-gimbal-login-" + UUID.randomUUID(), 1);
        String gimbalToken = fx.loginGimbal(mockMvc, gimbal2);
        MvcResult cloud = getExecutions(gimbalToken, memberId, "");
        assertEquals(403, cloud.getResponse().getStatus());
        assertEquals("CALLER_NOT_ALLOWED",
                JSON.readTree(cloud.getResponse().getContentAsString()).path("error").path("code").asText());
    }

    // ---------------- F2：A08 云台须当前核验上下文 ----------------

    @Test
    @DisplayName("F2 A08 云台：代次相等但生命周期/连续性不满足 → 404")
    void f2GimbalRequiresCurrentVerifiedContext() throws Exception {
        UUID gimbalId = fx.seedGimbal("f2-a08-login-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 8, 2, 1, null);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID executionId = fx.seedGimbalExecution(planId, memberId, fx.seedMicrocrystal(),
                assessment, gimbalId);
        jdbc.update("UPDATE care_executions SET verification_revision=5 WHERE id=?", executionId);
        String query = "?executionId=" + executionId + "&verificationRevision=5";

        assertEquals(200, getProgress(token, planId, query).getResponse().getStatus());

        String invalidated = "{\"schema_version\":1,\"epoch\":\"e\",\"seq\":\"5\","
                + "\"state\":\"paused\",\"occurred_at\":\"2026-09-10T04:00:05Z\","
                + "\"continuity_invalidated\":true}";
        jdbc.update("UPDATE care_executions SET status='paused', latest_observation=CAST(? AS jsonb)"
                + " WHERE id=?", invalidated, executionId);
        assertEquals(404, getProgress(token, planId, query).getResponse().getStatus());

        String valid = "{\"schema_version\":1,\"epoch\":\"e\",\"seq\":\"5\","
                + "\"state\":\"paused\",\"occurred_at\":\"2026-09-10T04:00:05Z\","
                + "\"continuity_invalidated\":false}";
        jdbc.update("UPDATE care_executions SET status='paused', latest_observation=CAST(? AS jsonb)"
                + " WHERE id=?", valid, executionId);
        assertEquals(200, getProgress(token, planId, query).getResponse().getStatus());

        jdbc.update("UPDATE care_executions SET status='stopped' WHERE id=?", executionId);
        assertEquals(404, getProgress(token, planId, query).getResponse().getStatus());

        jdbc.update("UPDATE care_executions SET status='closed', closed_at=now() WHERE id=?", executionId);
        assertEquals(404, getProgress(token, planId, query).getResponse().getStatus());

        jdbc.update("UPDATE care_executions SET status='unknown', closed_at=NULL WHERE id=?", executionId);
        assertEquals(404, getProgress(token, planId, query).getResponse().getStatus());
    }
}

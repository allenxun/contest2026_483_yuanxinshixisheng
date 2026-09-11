package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import cn.yuanxin.mvp.web.testdouble.FaceProviderDouble;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.CAPTURED_AT;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.PNG;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.capture;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/** M4-A04 连续性失效后重新核验集成测试（真实 PG；原控制端 + paused + 代次重检）。 */
class CareRevalidationIT extends AbstractWebIT {

    private static final String LATEST_OBS = "{\"schema_version\":1,\"epoch\":\"epoch-1\","
            + "\"seq\":\"2\",\"state\":\"paused\",\"occurred_at\":\"2026-09-10T04:00:00Z\","
            + "\"verification_revision\":\"1\",\"continuity_valid\":false,"
            + "\"continuity_invalidated\":true}";

    private static final String LATEST_VERIFICATION = "{\"schema_version\":1,"
            + "\"capture_id\":\"old-cap\",\"client_continuity_id\":\"old-cc\","
            + "\"verified_at\":\"2026-09-10T04:00:00Z\",\"valid_until\":null,"
            + "\"applicable_purpose\":\"admission\","
            + "\"media_id\":\"00000000-0000-0000-0000-0000000000aa\","
            + "\"classification\":\"MATCHED\",\"continuity_invalidated\":false}";

    private static final String SNAPSHOT = "{\"schema_version\":1,"
            + "\"plan_id\":\"00000000-0000-0000-0000-000000000001\",\"target_count\":\"5\","
            + "\"summary\":null,\"execution_params\":{\"title\":\"快照方案\"},"
            + "\"verification\":{\"purpose\":\"admission\"}}";

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    FaceProvider faceProvider;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private FaceProviderDouble faceDouble() {
        return (FaceProviderDouble) faceProvider;
    }

    private UUID seedPausedApp(UUID planId, UUID memberId, UUID accountId, String installation,
                               UUID assessment, UUID microcrystal) {
        return fx.execution(planId, memberId, microcrystal, assessment)
                .controllerApp(accountId, installation)
                .status("paused")
                .verificationRevision(1)
                .observation("epoch-1", 2, LATEST_OBS)
                .planSnapshot(SNAPSHOT)
                .latestVerification(LATEST_VERIFICATION)
                .lastVerifiedAt(Instant.parse("2026-09-10T04:00:00Z"))
                .insert();
    }

    private String metadata(String expectedRevision) {
        return CareAdmissionTestSupport.revalidationMetadata(expectedRevision,
                capture("cap-" + UUID.randomUUID(), CAPTURED_AT, "cc-new", "revalidation"),
                "consent-rev", null);
    }

    private JsonNode data(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("data");
    }

    private JsonNode error(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error");
    }

    // ---------------- happy path ----------------

    @Test
    @DisplayName("A04 paused 快乐路径 200：revision+1、仍 paused、最新核验与观测连续性失效消除")
    void a04PausedHappyPath() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a04-ok");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a04-ok-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 1, 1, null);
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID microcrystal = fx.seedMicrocrystal();
        UUID executionId = seedPausedApp(planId, memberId, accountId, "inst-a04-ok", assessment,
                microcrystal);

        String key = CareAdmissionTestSupport.newKey();
        MvcResult r = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(), executionId,
                key, metadata("1"), PNG);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        JsonNode d = data(r);
        assertEquals(executionId.toString(), d.path("executionId").asText());
        assertEquals("paused", d.path("status").asText());
        assertEquals(planId.toString(), d.path("planId").asText());
        assertEquals("快照方案", d.path("planExecution").path("title").asText());
        assertEquals("5", d.path("progress").path("targetCount").asText());
        JsonNode verification = d.path("verification");
        assertEquals("2", verification.path("verificationRevision").asText());
        assertEquals("revalidation", verification.path("applicablePurpose").asText());
        assertFalse(verification.path("replayed").asBoolean(true));
        assertTrue(verification.path("validUntil").isNull());

        Map<String, Object> row = jdbc.queryForMap("SELECT status, verification_revision,"
                + " latest_verification::text AS lv, latest_observation::text AS lo"
                + " FROM care_executions WHERE id = ?", executionId);
        assertEquals("paused", row.get("status"));
        assertEquals(2L, ((Number) row.get("verification_revision")).longValue());
        String latestVerification = (String) row.get("lv");
        assertTrue(latestVerification.contains("\"applicable_purpose\": \"revalidation\"")
                || latestVerification.contains("\"applicable_purpose\":\"revalidation\""));
        String latestObservation = (String) row.get("lo");
        assertTrue(latestObservation.contains("\"continuity_invalidated\": false")
                || latestObservation.contains("\"continuity_invalidated\":false"));

        UUID t13Id = jdbc.queryForObject("SELECT id FROM idempotency_requests WHERE idempotency_key = ?",
                UUID.class, key);
        Map<String, Object> media = jdbc.queryForMap("SELECT state, execution_id, member_id"
                + " FROM media_objects WHERE purpose = 'revalidation_face' AND request_id = ?", t13Id);
        assertEquals("available", media.get("state"));
        assertEquals(executionId, media.get("execution_id"));
        assertEquals(memberId, media.get("member_id"));
    }

    @Test
    @DisplayName("A04 后 A08 云台上下文：新代次 200、旧代次 404")
    void a04ThenGimbalProgressContext() throws Exception {
        UUID gimbalId = fx.seedGimbal("a04-a08-login-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 5, 1, 1, null);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID microcrystal = fx.seedMicrocrystal();
        UUID executionId = fx.execution(planId, memberId, microcrystal, assessment)
                .controllerGimbal(gimbalId)
                .status("paused").verificationRevision(1)
                .observation("epoch-g", 2, LATEST_OBS)
                .planSnapshot(SNAPSHOT)
                .latestVerification(LATEST_VERIFICATION)
                .lastVerifiedAt(Instant.parse("2026-09-10T04:00:00Z"))
                .insert();

        MvcResult r = CareAdmissionTestSupport.revalidate(mockMvc, token, executionId,
                CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("2", data(r).path("verification").path("verificationRevision").asText());

        MvcResult fresh = mockMvc.perform(get("/api/v1/care-plans/" + planId + "/progress")
                        .param("executionId", executionId.toString())
                        .param("verificationRevision", "2")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(200, fresh.getResponse().getStatus(), fresh.getResponse().getContentAsString());

        MvcResult stale = mockMvc.perform(get("/api/v1/care-plans/" + planId + "/progress")
                        .param("executionId", executionId.toString())
                        .param("verificationRevision", "1")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(404, stale.getResponse().getStatus());
    }

    // ---------------- rejections ----------------

    @Test
    @DisplayName("A04 expectedRevision 不符 → 409 verification_revision_mismatch")
    void a04RevisionMismatch() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a04-rev");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a04-rev-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID executionId = seedPausedApp(planId, memberId, accountId, "inst-a04-rev",
                fx.seedAssessment(gimbalId, memberId), fx.seedMicrocrystal());

        MvcResult r = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(), executionId,
                CareAdmissionTestSupport.newKey(), metadata("2"), PNG);
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("EXECUTION_NOT_RESUMABLE", error(r).path("code").asText());
        assertEquals("verification_revision_mismatch", error(r).path("details").path("reason").asText());
    }

    @Test
    @DisplayName("A04 status running/stopped/closed/unknown/admitted → 409 有界 reason")
    void a04StatusReasons() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a04-status");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a04-status-g-" + UUID.randomUUID(), 1);

        assertReason(login, accountId, memberId, gimbalId, "running", null, "running_not_paused");
        assertReason(login, accountId, memberId, gimbalId, "unknown", null,
                "unknown_needs_fresh_paused_observation");
        assertReason(login, accountId, memberId, gimbalId, "stopped", null, "stopped_not_resumable");
        assertReason(login, accountId, memberId, gimbalId, "closed",
                Instant.parse("2026-09-10T05:00:00Z"), "closed_not_resumable");
        assertReason(login, accountId, memberId, gimbalId, "admitted", null, "admitted_not_paused");
    }

    private void assertReason(LoginResult login, UUID accountId, UUID memberId, UUID gimbalId,
                              String status, Instant closedAt, String expectedReason) throws Exception {
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        var builder = fx.execution(planId, memberId, fx.seedMicrocrystal(),
                        fx.seedAssessment(gimbalId, memberId))
                .controllerApp(accountId, "inst-a04-status").status(status)
                .verificationRevision(1).planSnapshot(SNAPSHOT);
        if (closedAt != null) {
            builder.closedAt(closedAt);
        }
        UUID executionId = builder.insert();
        MvcResult r = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(), executionId,
                CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(409, r.getResponse().getStatus(), status + ": " + r.getResponse().getContentAsString());
        assertEquals(expectedReason, error(r).path("details").path("reason").asText(), status);
    }

    @Test
    @DisplayName("A04 K>=N paused → 409 plan_completed（不得用 PLAN_COMPLETED）")
    void a04PlanCompleted() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a04-done");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a04-done-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 3, 3, 2, null);
        UUID executionId = seedPausedApp(planId, memberId, accountId, "inst-a04-done",
                fx.seedAssessment(gimbalId, memberId), fx.seedMicrocrystal());

        MvcResult r = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(), executionId,
                CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("EXECUTION_NOT_RESUMABLE", error(r).path("code").asText());
        assertEquals("plan_completed", error(r).path("details").path("reason").asText());
    }

    @Test
    @DisplayName("A04 非原控制端（换安装/换账号/换云台/APP 对 gimbal）→ 404 与不存在 id 全等")
    void a04NonControllerNotFoundEqual() throws Exception {
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-a04-owner");
        UUID accountId = UUID.fromString(owner.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a04-own-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID executionId = seedPausedApp(planId, memberId, accountId, "inst-a04-owner",
                fx.seedAssessment(gimbalId, memberId), fx.seedMicrocrystal());

        MvcResult missing = CareAdmissionTestSupport.revalidate(mockMvc, owner.accessToken(),
                UUID.randomUUID(), CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(404, missing.getResponse().getStatus());
        String baseline = CareTestFixtures.errorTree(missing);

        // 同账号不同安装
        LoginResult otherInstall = loginAppWithInstallation(
                jdbc.queryForObject("SELECT login_subject FROM accounts WHERE id = ?", String.class, accountId),
                "inst-a04-other");
        MvcResult wrongInstall = CareAdmissionTestSupport.revalidate(mockMvc, otherInstall.accessToken(),
                executionId, CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(404, wrongInstall.getResponse().getStatus());
        assertEquals(baseline, CareTestFixtures.errorTree(wrongInstall));

        // 其他有授权的账号
        LoginResult otherAccount = loginAppWithInstallation(newPhone(), "inst-a04-other-acct");
        fx.seedGrant(UUID.fromString(otherAccount.accountId()), memberId, "active");
        MvcResult wrongAccount = CareAdmissionTestSupport.revalidate(mockMvc, otherAccount.accessToken(),
                executionId, CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(404, wrongAccount.getResponse().getStatus());
        assertEquals(baseline, CareTestFixtures.errorTree(wrongAccount));

        // 不同云台
        UUID otherGimbal = fx.seedGimbal("a04-other-g-" + UUID.randomUUID(), 1);
        String otherGimbalToken = fx.loginGimbal(mockMvc, otherGimbal);
        MvcResult wrongGimbal = CareAdmissionTestSupport.revalidate(mockMvc, otherGimbalToken,
                executionId, CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(404, wrongGimbal.getResponse().getStatus());
        assertEquals(baseline, CareTestFixtures.errorTree(wrongGimbal));

        // APP 对 gimbal 执行
        UUID gimbalExecAssessment = fx.seedAssessment(gimbalId, memberId);
        UUID gimbalPlan = fx.seedReadyPlan(gimbalExecAssessment, memberId, 5, 0, 0, null);
        UUID gimbalExecution = fx.execution(gimbalPlan, memberId, fx.seedMicrocrystal(),
                        gimbalExecAssessment)
                .controllerGimbal(gimbalId).status("paused").verificationRevision(1)
                .observation("epoch-x", 1, LATEST_OBS).planSnapshot(SNAPSHOT).insert();
        MvcResult appOnGimbal = CareAdmissionTestSupport.revalidate(mockMvc, owner.accessToken(),
                gimbalExecution, CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(404, appOnGimbal.getResponse().getStatus());
        assertEquals(baseline, CareTestFixtures.errorTree(appOnGimbal));
    }

    @Test
    @DisplayName("A04 APP 控制端授权已撤销 → 404")
    void a04RevokedGrant() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a04-revoked");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a04-revoked-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID executionId = seedPausedApp(planId, memberId, accountId, "inst-a04-revoked",
                fx.seedAssessment(gimbalId, memberId), fx.seedMicrocrystal());
        fx.revokeGrant(accountId, memberId);

        MvcResult r = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(), executionId,
                CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(404, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("RESOURCE_NOT_VISIBLE", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A04 云台任务已替换 → 409 TASK_REPLACED")
    void a04GimbalTaskReplaced() throws Exception {
        UUID gimbalId = fx.seedGimbal("a04-repl-login-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 5, 0, 0, null);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID executionId = fx.execution(planId, memberId, fx.seedMicrocrystal(), assessment)
                .controllerGimbal(gimbalId).status("paused").verificationRevision(1)
                .observation("epoch-g", 1, LATEST_OBS).planSnapshot(SNAPSHOT).insert();
        UUID otherAssessment = fx.seedAssessment(gimbalId, memberId);
        fx.pointGimbalAtAssessment(gimbalId, otherAssessment);

        MvcResult r = CareAdmissionTestSupport.revalidate(mockMvc, token, executionId,
                CareAdmissionTestSupport.newKey(), metadata("1"), PNG);
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("TASK_REPLACED", error(r).path("code").asText());
    }

    // ---------------- replay / face ----------------

    @Test
    @DisplayName("A04 同键重放 200：meta.replayed + verification.replayed，revision 不再递增")
    void a04Replay() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a04-replay");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a04-replay-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID executionId = seedPausedApp(planId, memberId, accountId, "inst-a04-replay",
                fx.seedAssessment(gimbalId, memberId), fx.seedMicrocrystal());

        String key = CareAdmissionTestSupport.newKey();
        String metadata = metadata("1");
        MvcResult first = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(), executionId,
                key, metadata, PNG);
        assertEquals(200, first.getResponse().getStatus(), first.getResponse().getContentAsString());
        assertEquals("2", data(first).path("verification").path("verificationRevision").asText());

        MvcResult replay = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(), executionId,
                key, metadata, PNG);
        assertEquals(200, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        JsonNode envelope = JSON.readTree(replay.getResponse().getContentAsString());
        assertTrue(envelope.path("meta").path("replayed").asBoolean());
        assertTrue(envelope.path("data").path("verification").path("replayed").asBoolean());
        assertEquals("2", envelope.path("data").path("verification")
                .path("verificationRevision").asText());
        assertEquals(2L, ((Number) jdbc.queryForObject(
                "SELECT verification_revision FROM care_executions WHERE id = ?", Long.class,
                executionId)).longValue());
    }

    @Test
    @DisplayName("A04 人脸 UNCERTAIN 403 rejected；DEPENDENCY_FAILED 503 processing")
    void a04FaceClassifications() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a04-face");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a04-face-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID executionId = seedPausedApp(planId, memberId, accountId, "inst-a04-face",
                fx.seedAssessment(gimbalId, memberId), fx.seedMicrocrystal());

        try {
            String key1 = CareAdmissionTestSupport.newKey();
            faceDouble().setClassification(FaceClassification.UNCERTAIN);
            MvcResult uncertain = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(),
                    executionId, key1, metadata("1"), PNG);
            assertEquals(403, uncertain.getResponse().getStatus(), uncertain.getResponse().getContentAsString());
            assertEquals("FACE_NOT_VERIFIED", error(uncertain).path("code").asText());
            assertEquals("rejected", jdbc.queryForObject(
                    "SELECT status FROM idempotency_requests WHERE idempotency_key = ?", String.class, key1));
            assertEquals(1L, ((Number) jdbc.queryForObject(
                    "SELECT verification_revision FROM care_executions WHERE id = ?", Long.class,
                    executionId)).longValue());

            String key2 = CareAdmissionTestSupport.newKey();
            faceDouble().setClassification(FaceClassification.DEPENDENCY_FAILED);
            MvcResult dependency = CareAdmissionTestSupport.revalidate(mockMvc, login.accessToken(),
                    executionId, key2, metadata("1"), PNG);
            assertEquals(503, dependency.getResponse().getStatus());
            assertEquals("DEPENDENCY_UNAVAILABLE", error(dependency).path("code").asText());
            assertEquals("processing", jdbc.queryForObject(
                    "SELECT status FROM idempotency_requests WHERE idempotency_key = ?", String.class, key2));
        } finally {
            faceDouble().setClassification(FaceClassification.MATCHED);
        }
    }
}

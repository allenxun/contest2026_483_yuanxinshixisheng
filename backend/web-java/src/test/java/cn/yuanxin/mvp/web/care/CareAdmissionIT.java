package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.care.CareFaceVerifier.Outcome;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.UUID;

import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.CAPTURED_AT;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.PNG;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.capture;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** M4-A03 登记新执行集成测试（真实 PG；锁外核验 + 最终短事务 + T13 重放）。 */
class CareAdmissionIT extends AbstractCareIT {

    private static final String CAPABILITIES = CareTestFixtures.DEFAULT_CAPABILITIES;

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private String appMetadata(UUID microcrystalId, String proof, UUID planId) {
        return CareAdmissionTestSupport.admissionMetadata(microcrystalId, proof, planId, null, null,
                capture("cap-" + UUID.randomUUID(), CAPTURED_AT, "cc-1", "admission"), "consent-1");
    }

    private JsonNode data(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("data");
    }

    private JsonNode error(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error");
    }

    private UUID t13IdOf(String key) {
        return jdbc.queryForObject("SELECT id FROM idempotency_requests WHERE idempotency_key = ?",
                UUID.class, key);
    }

    // ---------------- happy paths ----------------

    @Test
    @DisplayName("A03 APP 快乐路径 201：响应字段齐全、T07/T13/T11 落库与归属补齐")
    void a03AppHappyPath() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a03-app");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        bindFaceMember(memberId);
        UUID gimbalId = fx.seedGimbal("a03-app-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 1, 1, null);
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);

        String key = CareAdmissionTestSupport.newKey();
        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key,
                appMetadata(microcrystalId, "proof-1", planId), PNG);
        assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));

        JsonNode d = data(r);
        UUID executionId = UUID.fromString(d.path("executionId").asText());
        assertEquals("admitted", d.path("status").asText());
        assertEquals("app_account", d.path("controller").path("controllerType").asText());
        assertEquals("inst-a03-app", d.path("controller").path("installationId").asText());
        assertTrue(d.path("controller").path("gimbalId").isNull());
        assertEquals(memberId.toString(), d.path("memberId").asText());
        assertEquals(planId.toString(), d.path("planId").asText());
        // F3：Plan.execution 白名单仅 steps/regions/parameters；title/schema_version 不外发
        assertEquals(1, d.path("planExecution").path("steps").size());
        assertTrue(d.path("planExecution").path("title").isMissingNode());
        assertTrue(d.path("planExecution").path("schema_version").isMissingNode());
        JsonNode progress = d.path("progress");
        assertEquals("5", progress.path("targetCount").asText());
        assertEquals("1", progress.path("completedCount").asText());
        assertEquals("4", progress.path("remainingCount").asText());
        assertFalse(progress.path("isCompleted").asBoolean(true));
        JsonNode verification = d.path("verification");
        assertEquals("1", verification.path("verificationRevision").asText());
        assertEquals("admission", verification.path("applicablePurpose").asText());
        assertFalse(verification.path("replayed").asBoolean(true));
        assertTrue(verification.path("validUntil").isNull());
        assertEquals(executionId.toString(), d.path("recordStreamEpoch").asText());

        Map<String, Object> row = jdbc.queryForMap("SELECT * FROM care_executions WHERE id = ?",
                executionId);
        assertEquals("admitted", row.get("status"));
        assertEquals(1L, ((Number) row.get("verification_revision")).longValue());
        assertEquals(executionId.toString(), row.get("observation_epoch"));
        assertEquals(0L, ((Number) row.get("accepted_count")).longValue());
        assertEquals(memberId, row.get("member_id"));

        UUID t13Id = t13IdOf(key);
        assertEquals(t13Id, row.get("source_request_id"));
        Map<String, Object> t13 = jdbc.queryForMap(
                "SELECT status, resource_type, resource_id FROM idempotency_requests WHERE id = ?",
                t13Id);
        assertEquals("succeeded", t13.get("status"));
        assertEquals("care_execution", t13.get("resource_type"));
        assertEquals(executionId, t13.get("resource_id"));

        String snapshot = jdbc.queryForObject(
                "SELECT plan_snapshot::text FROM care_executions WHERE id = ?", String.class,
                executionId);
        assertTrue(snapshot.contains("\"schema_version\": 1") || snapshot.contains("\"schema_version\":1"));
        assertTrue(snapshot.contains("\"target_count\": \"5\""));

        Map<String, Object> face = jdbc.queryForMap("SELECT state, purpose, execution_id, member_id"
                + " FROM media_objects WHERE purpose = 'execution_face' AND request_id = ?", t13Id);
        assertEquals("available", face.get("state"));
        assertEquals("execution_face", face.get("purpose"));
        assertEquals(executionId, face.get("execution_id"));
        assertEquals(memberId, face.get("member_id"));
    }

    @Test
    @DisplayName("A03 云台快乐路径 201：由当前任务解析方案，gimbal 控制端归属")
    void a03GimbalHappyPath() throws Exception {
        UUID gimbalId = fx.seedGimbal("a03-gimbal-login-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        bindFaceMember(memberId);
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 4, 0, 0, null);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);

        String key = CareAdmissionTestSupport.newKey();
        String metadata = CareAdmissionTestSupport.admissionMetadata(microcrystalId, "proof-g",
                null, assessment, "1",
                capture("cap-g", CAPTURED_AT, "cc-g", "admission"), "consent-g");
        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, token, key, metadata, PNG);
        assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        UUID executionId = UUID.fromString(d.path("executionId").asText());
        assertEquals("gimbal", d.path("controller").path("controllerType").asText());
        assertEquals(gimbalId.toString(), d.path("controller").path("gimbalId").asText());
        assertTrue(d.path("controller").path("installationId").isNull());
        assertEquals(planId.toString(), d.path("planId").asText());
        assertEquals(memberId.toString(), d.path("memberId").asText());

        Map<String, Object> row = jdbc.queryForMap("SELECT * FROM care_executions WHERE id = ?",
                executionId);
        assertEquals("gimbal", row.get("controller_type"));
        assertEquals(gimbalId, row.get("controller_gimbal_id"));
        assertNull(row.get("controller_account_id"));
        assertNull(row.get("controller_installation_id"));
    }

    // ---------------- idempotency ----------------

    @Test
    @DisplayName("A03 同键同内容重放 200 同 executionId + replayed，且不刷新核验；异内容 409")
    void a03ReplayAndContentConflict() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a03-replay");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        bindFaceMember(memberId);
        UUID gimbalId = fx.seedGimbal("a03-replay-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 1, 1, null);
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);

        String key = CareAdmissionTestSupport.newKey();
        String metadata = appMetadata(microcrystalId, "proof-r", planId);
        MvcResult first = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key, metadata, PNG);
        assertEquals(201, first.getResponse().getStatus(), first.getResponse().getContentAsString());
        UUID executionId = UUID.fromString(data(first).path("executionId").asText());
        Map<String, Object> before = jdbc.queryForMap("SELECT verification_revision, last_verified_at,"
                + " latest_verification::text AS lv FROM care_executions WHERE id = ?", executionId);

        MvcResult second = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key, metadata, PNG);
        assertEquals(200, second.getResponse().getStatus(), second.getResponse().getContentAsString());
        JsonNode envelope = JSON.readTree(second.getResponse().getContentAsString());
        assertTrue(envelope.path("meta").path("replayed").asBoolean());
        JsonNode d = envelope.path("data");
        assertEquals(executionId.toString(), d.path("executionId").asText());
        assertEquals("admitted", d.path("status").asText());
        assertTrue(d.path("verification").path("replayed").asBoolean());
        assertEquals("1", d.path("verification").path("verificationRevision").asText());

        Map<String, Object> after = jdbc.queryForMap("SELECT verification_revision, last_verified_at,"
                + " latest_verification::text AS lv FROM care_executions WHERE id = ?", executionId);
        assertEquals(before, after);

        // 同键异内容（connectionProof 变化）→ 409
        String changed = appMetadata(microcrystalId, "proof-CHANGED", planId);
        MvcResult conflict = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key, changed, PNG);
        assertEquals(409, conflict.getResponse().getStatus(), conflict.getResponse().getContentAsString());
        assertEquals("IDEMPOTENCY_CONTENT_CONFLICT", error(conflict).path("code").asText());
    }

    @Test
    @DisplayName("A03 确定性拒绝写 T13 rejected 且同键重放原 409；缺 Idempotency-Key 400")
    void a03DeterministicRejectionReplayAndMissingKey() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a03-rej");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        bindFaceMember(memberId);
        UUID gimbalId = fx.seedGimbal("a03-rej-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedWaitingPlan(fx.seedAssessment(gimbalId, memberId), memberId, "{}");
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);
        String metadata = appMetadata(microcrystalId, "proof-rej", planId);

        String key = CareAdmissionTestSupport.newKey();
        MvcResult first = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key, metadata, PNG);
        assertEquals(409, first.getResponse().getStatus(), first.getResponse().getContentAsString());
        assertEquals("PLAN_NOT_READY", error(first).path("code").asText());
        assertEquals("rejected", jdbc.queryForObject(
                "SELECT status FROM idempotency_requests WHERE idempotency_key = ?", String.class, key));

        MvcResult replay = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key, metadata, PNG);
        assertEquals(409, replay.getResponse().getStatus());
        assertEquals("PLAN_NOT_READY", error(replay).path("code").asText());

        MvcResult missing = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), null,
                metadata, PNG);
        assertEquals(400, missing.getResponse().getStatus(), missing.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(missing).path("code").asText());
    }

    // ---------------- validation / authorization ----------------

    @Test
    @DisplayName("A03 角色化 metadata 校验：APP 带任务/缺 planId、GIMBAL 带 planId、purpose 非 admission 均 400")
    void a03RoleAndPurposeValidation() throws Exception {
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a03-role");
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);
        UUID randomPlan = UUID.randomUUID();
        UUID randomTask = UUID.randomUUID();

        MvcResult appWithTask = CareAdmissionTestSupport.admit(mockMvc, app.accessToken(),
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(microcrystalId, "p", randomPlan,
                        randomTask, "1", capture("c", CAPTURED_AT, "cc", "admission"), "consent"),
                PNG);
        assertEquals(400, appWithTask.getResponse().getStatus());

        MvcResult appMissingPlan = CareAdmissionTestSupport.admit(mockMvc, app.accessToken(),
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(microcrystalId, "p", null, null, null,
                        capture("c", CAPTURED_AT, "cc", "admission"), "consent"),
                PNG);
        assertEquals(400, appMissingPlan.getResponse().getStatus());

        MvcResult wrongPurpose = CareAdmissionTestSupport.admit(mockMvc, app.accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(microcrystalId, "p", randomPlan)
                        .replace("\"admission\"", "\"grant\""), PNG);
        assertEquals(400, wrongPurpose.getResponse().getStatus());

        UUID gimbalId = fx.seedGimbal("a03-role-g-" + UUID.randomUUID(), 1);
        String gimbalToken = fx.loginGimbal(mockMvc, gimbalId);
        MvcResult gimbalWithPlan = CareAdmissionTestSupport.admit(mockMvc, gimbalToken,
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(microcrystalId, "p", randomPlan,
                        randomTask, "1", capture("c", CAPTURED_AT, "cc", "admission"), "consent"),
                PNG);
        assertEquals(400, gimbalWithPlan.getResponse().getStatus());
    }

    @Test
    @DisplayName("A03 无授权 APP 404 与随机 planId 404 信封全等")
    void a03Authorization404Equality() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a03-404");
        UUID memberId = fx.seedMember();
        UUID gimbalId = fx.seedGimbal("a03-404-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);

        MvcResult noGrant = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(microcrystalId, "p", planId), PNG);
        assertEquals(404, noGrant.getResponse().getStatus());
        MvcResult randomPlan = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(microcrystalId, "p", UUID.randomUUID()), PNG);
        assertEquals(404, randomPlan.getResponse().getStatus());
        assertEquals(CareTestFixtures.errorTree(noGrant), CareTestFixtures.errorTree(randomPlan));
    }

    // ---------------- task / plan / device ----------------

    @Test
    @DisplayName("A03 云台任务代次/任务不符 → 409 TASK_REPLACED")
    void a03GimbalTaskReplaced() throws Exception {
        UUID gimbalId = fx.seedGimbal("a03-repl-login-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        fx.seedReadyPlan(assessment, memberId, 5, 0, 0, null);
        UUID otherAssessment = fx.seedAssessment(gimbalId, memberId);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);

        MvcResult revisionMismatch = CareAdmissionTestSupport.admit(mockMvc, token,
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(microcrystalId, "p", null, assessment, "2",
                        capture("c", CAPTURED_AT, "cc", "admission"), "consent"),
                PNG);
        assertEquals(409, revisionMismatch.getResponse().getStatus());
        assertEquals("TASK_REPLACED", error(revisionMismatch).path("code").asText());

        MvcResult taskMismatch = CareAdmissionTestSupport.admit(mockMvc, token,
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(microcrystalId, "p", null, otherAssessment, "1",
                        capture("c", CAPTURED_AT, "cc", "admission"), "consent"),
                PNG);
        assertEquals(409, taskMismatch.getResponse().getStatus());
        assertEquals("TASK_REPLACED", error(taskMismatch).path("code").asText());
    }

    @Test
    @DisplayName("A03 K>=N → 409 PLAN_COMPLETED")
    void a03PlanCompleted() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a03-done");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        bindFaceMember(memberId);
        UUID gimbalId = fx.seedGimbal("a03-done-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 3, 3, 2, null);
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);

        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(microcrystalId, "p", planId), PNG);
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("PLAN_COMPLETED", error(r).path("code").asText());
    }

    @Test
    @DisplayName("A03 能力覆盖（D 约定）：各类不符→409 token；revision 不同仍 201（非门禁）")
    void a03CapabilityChecker() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a03-cap");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        bindFaceMember(memberId);
        UUID gimbalId = fx.seedGimbal("a03-cap-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);

        MvcResult missing = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(UUID.randomUUID(), "p", planId), PNG);
        assertEquals(404, missing.getResponse().getStatus());

        assertCapabilityReason(login, planId, fx.seedMicrocrystal("{}"),
                "device_capabilities_missing");
        assertCapabilityReason(login, planId,
                fx.seedMicrocrystal(device("other-cap", "0", "8", "[\"face\",\"neck\"]")),
                "capability_id_mismatch");
        assertCapabilityReason(login, planId,
                fx.seedMicrocrystal(device("cap-mvp-1", "0", "3", "[\"face\",\"neck\"]")),
                "parameter_range_not_covered");
        assertCapabilityReason(login, planId,
                fx.seedMicrocrystal(device("cap-mvp-1", "0", "8", "[\"neck\"]")),
                "region_not_supported");

        // 冻结快照缺 capability 块 → fail-closed
        UUID noSnapshotPlan = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        fx.setPlanInputSnapshot(noSnapshotPlan, "{}");
        assertCapabilityReason(login, noSnapshotPlan, fx.seedMicrocrystal(CAPABILITIES),
                "frozen_capability_requirement_missing");

        // N 越冻结 n_bounds 上界（max 30）
        UUID bigPlan = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 40, 0, 0, null);
        assertCapabilityReason(login, bigPlan, fx.seedMicrocrystal(CAPABILITIES), "n_out_of_bounds");

        // 正例：设备 revision 9 ≠ 冻结 7，但其余覆盖 → 201（revision 仅追溯）
        bindFaceMember(memberId);
        MvcResult matched = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(),
                appMetadata(fx.seedMicrocrystal(CAPABILITIES), "p", planId), PNG);
        assertEquals(201, matched.getResponse().getStatus(), matched.getResponse().getContentAsString());
    }

    private void assertCapabilityReason(LoginResult login, UUID planId, UUID microcrystalId,
                                        String expectedReason) throws Exception {
        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(microcrystalId, "p", planId), PNG);
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("PLAN_NOT_READY", error(r).path("code").asText());
        assertEquals(expectedReason, error(r).path("details").path("reason").asText());
    }

    private static String device(String capabilityId, String min, String max, String regionsJson) {
        return "{\"schema_version\":1,\"capability_id\":\"" + capabilityId + "\",\"revision\":\"9\","
                + "\"parameter_ranges\":{\"intensity\":{\"min\":\"" + min + "\",\"max\":\"" + max
                + "\",\"unit\":\"level\"}},\"supported_regions\":" + regionsJson + "}";
    }

    // ---------------- face / media ----------------

    @Test
    @DisplayName("A03 人脸 UNCERTAIN 403 rejected 无执行；QUALITY_REJECTED 422；DEPENDENCY_FAILED 503 processing；非图片 415")
    void a03FaceClassificationsAndBadImage() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a03-face");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        bindFaceMember(memberId);
        UUID gimbalId = fx.seedGimbal("a03-face-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);

        try {
            UUID mic1 = fx.seedMicrocrystal(CAPABILITIES);
            String key1 = CareAdmissionTestSupport.newKey();
            faceDouble.forceOutcome(Outcome.UNCERTAIN);
            MvcResult uncertain = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key1,
                    appMetadata(mic1, "p", planId), PNG);
            assertEquals(403, uncertain.getResponse().getStatus(), uncertain.getResponse().getContentAsString());
            assertEquals("FACE_NOT_VERIFIED", error(uncertain).path("code").asText());
            assertEquals("rejected", jdbc.queryForObject(
                    "SELECT status FROM idempotency_requests WHERE idempotency_key = ?", String.class, key1));
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM care_executions WHERE microcrystal_id = ?",
                    Integer.class, mic1));

            UUID mic2 = fx.seedMicrocrystal(CAPABILITIES);
            faceDouble.forceOutcome(Outcome.QUALITY_REJECTED);
            MvcResult quality = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                    CareAdmissionTestSupport.newKey(),
                    appMetadata(mic2, "p", planId), PNG);
            assertEquals(422, quality.getResponse().getStatus());
            assertEquals("FACE_QUALITY_REJECTED", error(quality).path("code").asText());

            UUID mic3 = fx.seedMicrocrystal(CAPABILITIES);
            String key3 = CareAdmissionTestSupport.newKey();
            faceDouble.forceOutcome(Outcome.DEPENDENCY_FAILED);
            MvcResult dependency = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key3,
                    appMetadata(mic3, "p", planId), PNG);
            assertEquals(503, dependency.getResponse().getStatus());
            assertEquals("DEPENDENCY_UNAVAILABLE", error(dependency).path("code").asText());
            assertEquals("processing", jdbc.queryForObject(
                    "SELECT status FROM idempotency_requests WHERE idempotency_key = ?", String.class, key3));
        } finally {
            faceDouble.reset();
        }

        UUID mic4 = fx.seedMicrocrystal(CAPABILITIES);
        MvcResult badImage = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(mic4, "p", planId),
                CareAdmissionTestSupport.NOT_IMAGE);
        assertEquals(415, badImage.getResponse().getStatus(), badImage.getResponse().getContentAsString());
        assertEquals("UNSUPPORTED_IMAGE", error(badImage).path("code").asText());
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM care_executions WHERE microcrystal_id = ?",
                Integer.class, mic4));
    }

    // ---------------- F1：重放须当前读取资格 ----------------

    @Test
    @DisplayName("F1 A03 APP 重放：撤销授权后同键重放 404（与随机 id 全等），T13 仍 succeeded")
    void f1AdmissionReplayRequiresCurrentGrant() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-f1-a03");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        bindFaceMember(memberId);
        UUID gimbalId = fx.seedGimbal("f1-a03-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 1, 1, null);
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);
        String key = CareAdmissionTestSupport.newKey();
        String metadata = appMetadata(microcrystalId, "proof-f1", planId);
        MvcResult first = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key, metadata, PNG);
        assertEquals(201, first.getResponse().getStatus(), first.getResponse().getContentAsString());

        fx.revokeGrant(accountId, memberId);
        MvcResult replay = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key, metadata, PNG);
        assertEquals(404, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        MvcResult random = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(microcrystalId, "p", UUID.randomUUID()), PNG);
        assertEquals(404, random.getResponse().getStatus());
        assertEquals(CareTestFixtures.errorTree(replay), CareTestFixtures.errorTree(random));
        assertEquals("succeeded", jdbc.queryForObject(
                "SELECT status FROM idempotency_requests WHERE idempotency_key = ?", String.class, key));
    }

    @Test
    @DisplayName("F1 A03 云台重放：任务指针换到另一 assessment 后同键重放 404")
    void f1AdmissionReplayRequiresCurrentTask() throws Exception {
        UUID gimbalId = fx.seedGimbal("f1-a03-gimbal-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        bindFaceMember(memberId);
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        fx.seedReadyPlan(assessment, memberId, 5, 0, 0, null);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID microcrystalId = fx.seedMicrocrystal(CAPABILITIES);
        String key = CareAdmissionTestSupport.newKey();
        String metadata = CareAdmissionTestSupport.admissionMetadata(microcrystalId, "pg", null,
                assessment, "1",
                CareAdmissionTestSupport.capture("c", "2026-09-10T04:00:00Z", "cc", "admission"),
                "consent");
        MvcResult first = CareAdmissionTestSupport.admit(mockMvc, token, key, metadata, PNG);
        assertEquals(201, first.getResponse().getStatus(), first.getResponse().getContentAsString());

        UUID otherAssessment = fx.seedAssessment(gimbalId, memberId);
        fx.pointGimbalAtAssessment(gimbalId, otherAssessment);
        MvcResult replay = CareAdmissionTestSupport.admit(mockMvc, token, key, metadata, PNG);
        assertEquals(404, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
    }

    // ---------------- Part 2：存储本树化 ----------------

    @Test
    @DisplayName("Part2 人脸文件写入本工作树 target/c-test-storage，不在 /tmp/mvp-a-test-storage")
    void careStorageRootedInWorktree() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-store");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        bindFaceMember(memberId);
        UUID gimbalId = fx.seedGimbal("store-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);
        String key = CareAdmissionTestSupport.newKey();
        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(), key,
                appMetadata(micro, "p", planId), PNG);
        assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());

        UUID t13 = t13IdOf(key);
        String objectKey = jdbc.queryForObject("SELECT object_key FROM media_objects"
                + " WHERE purpose = 'execution_face' AND request_id = ?", String.class, t13);
        java.nio.file.Path rooted = java.nio.file.Path.of(storageDevDir).toAbsolutePath()
                .resolve(objectKey).normalize();
        assertTrue(java.nio.file.Files.isRegularFile(rooted), rooted.toString());
        assertFalse(java.nio.file.Files.isRegularFile(
                java.nio.file.Path.of("/tmp/mvp-a-test-storage").resolve(objectKey)));
    }
}

package cn.yuanxin.mvp.web.care;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.closureBody;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.recordJson;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.syncBody;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** M4-A06 收尾集成测试（真实 PG；停止确认 + 单表水位核对 + 释放占用 + T13 重放）。 */
class CareClosureIT extends AbstractCareIT {

    private static final String CAPABILITIES = CareTestFixtures.DEFAULT_CAPABILITIES;
    private static final String STOPPED_OBS = "{\"schema_version\":1,\"epoch\":\"epoch-1\","
            + "\"seq\":\"5\",\"state\":\"stopped\",\"occurred_at\":\"2026-09-10T04:00:05Z\","
            + "\"continuity_invalidated\":false}";

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private record Ctx(LoginResult login, UUID memberId, UUID planId, UUID micro, UUID assessment) {
    }

    private Ctx newCtx(String inst) throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), inst);
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("closure-g-" + UUID.randomUUID(), 1);
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 10, 0, 0, null);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);
        return new Ctx(login, memberId, planId, micro, assessment);
    }

    private UUID stoppedExecution(Ctx ctx, String inst, String status) {
        return stoppedExecution(ctx, inst, status, ctx.micro());
    }

    private UUID stoppedExecution(Ctx ctx, String inst, String status, UUID micro) {
        return fx.execution(ctx.planId(), ctx.memberId(), micro, ctx.assessment())
                .controllerApp(UUID.fromString(ctx.login().accountId()), inst)
                .status(status)
                .observation("epoch-1", 5L, STOPPED_OBS)
                .insert();
    }

    private void seedRecords(Ctx ctx, UUID executionId, long... seqs) {
        for (long seq : seqs) {
            fx.seedRecord(executionId, ctx.planId(), ctx.memberId(), ctx.micro(),
                    "r" + seq, "epoch-1", seq, 1);
        }
    }

    private MvcResult close(Ctx ctx, UUID executionId, String key, String body) throws Exception {
        return CareAdmissionTestSupport.postJson(mockMvc, ctx.login().accessToken(),
                "/api/v1/care-executions/" + executionId + "/closure-confirmations", key, body);
    }

    private MvcResult sync(Ctx ctx, UUID executionId, String key, String body) throws Exception {
        return CareAdmissionTestSupport.postJson(mockMvc, ctx.login().accessToken(),
                "/api/v1/care-executions/" + executionId + "/observations", key, body);
    }

    private static JsonNode data(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("data");
    }

    private static JsonNode error(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error");
    }

    private Map<String, Object> executionRow(UUID executionId) {
        return jdbc.queryForMap("SELECT status, closed_at, closure_manifest::text AS manifest"
                + " FROM care_executions WHERE id = ?", executionId);
    }

    private static String body(String stopSeq, String reason, String epoch, String w, String count) {
        return closureBody(stopSeq, reason, epoch, w, count);
    }

    // ---------------- happy paths ----------------

    @Test
    @DisplayName("A06 快乐收尾：200 closed/occupancyReleased、manifest 全字段、占用释放可新 A03")
    void a06HappyClosure() throws Exception {
        Ctx ctx = newCtx("inst-a06-ok");
        UUID executionId = stoppedExecution(ctx, "inst-a06-ok", "stopped");
        seedRecords(ctx, executionId, 1, 2, 3);

        MvcResult r = close(ctx, executionId, "c1", body("5", "user_finished", "epoch-1", "3", "3"));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertTrue(d.path("closed").asBoolean());
        assertTrue(d.path("occupancyReleased").asBoolean());
        assertFalse(d.path("closedAt").isNull());

        Map<String, Object> row = executionRow(executionId);
        assertEquals("closed", row.get("status"));
        assertNotNull(row.get("closed_at"));
        String manifest = (String) row.get("manifest");
        assertTrue(manifest.contains("\"schema_version\": 1") || manifest.contains("\"schema_version\":1"));
        assertTrue(manifest.contains("\"record_stream_epoch\": \"epoch-1\"")
                || manifest.contains("\"record_stream_epoch\":\"epoch-1\""));
        assertTrue(manifest.contains("\"final_record_seq\": \"3\"")
                || manifest.contains("\"final_record_seq\":\"3\""));
        assertTrue(manifest.contains("user_finished"));

        // 占用释放：同一微晶可再次准入
        bindFaceMember(ctx.memberId());
        MvcResult admission = CareAdmissionTestSupport.admit(mockMvc, ctx.login().accessToken(),
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(ctx.micro(), "p", ctx.planId(), null, null,
                        CareAdmissionTestSupport.capture("c", "2026-09-10T04:00:09Z", "cc", "admission"),
                        "consent"),
                CareAdmissionTestSupport.PNG);
        assertEquals(201, admission.getResponse().getStatus(), admission.getResponse().getContentAsString());
    }

    @Test
    @DisplayName("A06 W=0 空流：无记录 finalCount=0 → closed")
    void a06EmptyStream() throws Exception {
        Ctx ctx = newCtx("inst-a06-empty");
        UUID executionId = stoppedExecution(ctx, "inst-a06-empty", "stopped");
        MvcResult r = close(ctx, executionId, "ce", body("5", "user_finished", "epoch-1", "0", "0"));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertTrue(data(r).path("closed").asBoolean());
        assertEquals("closed", executionRow(executionId).get("status"));
    }

    // ---------------- gaps ----------------

    @Test
    @DisplayName("A06 缺口：记录 1,2,4 W=4 → 409 CLOSURE_GAPS missingRanges=[3,3]")
    void a06Gaps() throws Exception {
        Ctx ctx = newCtx("inst-a06-gaps");
        UUID executionId = stoppedExecution(ctx, "inst-a06-gaps", "stopped");
        seedRecords(ctx, executionId, 1, 2, 4);
        MvcResult r = close(ctx, executionId, "cg", body("5", "user_finished", "epoch-1", "4", "4"));
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("CLOSURE_GAPS", error(r).path("code").asText());
        assertEquals("gaps", error(r).path("details").path("reason").asText());
        JsonNode ranges = error(r).path("details").path("missingRanges");
        assertEquals(1, ranges.size());
        assertEquals("3", ranges.get(0).path("from").asText());
        assertEquals("3", ranges.get(0).path("to").asText());
        assertEquals("stopped", executionRow(executionId).get("status"));
    }

    @Test
    @DisplayName("A06 total≠finalCount → 409 count_mismatch")
    void a06CountMismatch() throws Exception {
        Ctx ctx = newCtx("inst-a06-count");
        UUID executionId = stoppedExecution(ctx, "inst-a06-count", "stopped");
        seedRecords(ctx, executionId, 1, 2, 3);
        MvcResult r = close(ctx, executionId, "cc", body("5", "user_finished", "epoch-1", "3", "4"));
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("CLOSURE_GAPS", error(r).path("code").asText());
        assertEquals("count_mismatch", error(r).path("details").path("reason").asText());
    }

    @Test
    @DisplayName("A06 max_seq>W → 409 max_seq_exceeds_final")
    void a06MaxSeqExceeds() throws Exception {
        Ctx ctx = newCtx("inst-a06-max");
        UUID executionId = stoppedExecution(ctx, "inst-a06-max", "stopped");
        seedRecords(ctx, executionId, 1, 2, 3, 4);
        MvcResult r = close(ctx, executionId, "cm", body("5", "user_finished", "epoch-1", "3", "3"));
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("max_seq_exceeds_final", error(r).path("details").path("reason").asText());
    }

    // ---------------- stop / epoch / status ----------------

    @Test
    @DisplayName("A06 非 stopped 状态 running/unknown/admitted → 409 STOP_NOT_CONFIRMED not_stopped")
    void a06NotStopped() throws Exception {
        Ctx ctx = newCtx("inst-a06-notstopped");
        for (String status : new String[]{"running", "unknown", "admitted"}) {
            UUID micro = fx.seedMicrocrystal(CAPABILITIES);
            UUID executionId = stoppedExecution(ctx, "inst-a06-notstopped", status, micro);
            MvcResult r = close(ctx, executionId, "ns-" + status,
                    body("5", "user_finished", "epoch-1", "0", "0"));
            assertEquals(409, r.getResponse().getStatus(), status);
            assertEquals("STOP_NOT_CONFIRMED", error(r).path("code").asText(), status);
            assertEquals("not_stopped", error(r).path("details").path("reason").asText(), status);
        }
    }

    @Test
    @DisplayName("A06 stopObservationSeq 不符 → 409 stop_observation_mismatch")
    void a06StopObservationMismatch() throws Exception {
        Ctx ctx = newCtx("inst-a06-stopmis");
        UUID executionId = stoppedExecution(ctx, "inst-a06-stopmis", "stopped");
        MvcResult r = close(ctx, executionId, "sm", body("4", "user_finished", "epoch-1", "0", "0"));
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("stop_observation_mismatch", error(r).path("details").path("reason").asText());
    }

    @Test
    @DisplayName("A06 epoch 不符 → 409 RECORD_CONFLICT epoch_mismatch")
    void a06EpochMismatch() throws Exception {
        Ctx ctx = newCtx("inst-a06-epoch");
        UUID executionId = stoppedExecution(ctx, "inst-a06-epoch", "stopped");
        MvcResult r = close(ctx, executionId, "em", body("5", "user_finished", "other", "0", "0"));
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("RECORD_CONFLICT", error(r).path("code").asText());
        assertEquals("epoch_mismatch", error(r).path("details").path("reason").asText());
    }

    // ---------------- replay / closed / visibility / validation ----------------

    @Test
    @DisplayName("A06 同键重放：200 同 closedAt、manifest 逐字节不变、meta.replayed")
    void a06Replay() throws Exception {
        Ctx ctx = newCtx("inst-a06-replay");
        UUID executionId = stoppedExecution(ctx, "inst-a06-replay", "stopped");
        seedRecords(ctx, executionId, 1, 2, 3);
        String request = body("5", "user_finished", "epoch-1", "3", "3");
        MvcResult first = close(ctx, executionId, "cr", request);
        assertEquals(200, first.getResponse().getStatus(), first.getResponse().getContentAsString());
        String manifestBefore = (String) executionRow(executionId).get("manifest");
        String closedAtBefore = data(first).path("closedAt").asText();

        MvcResult replay = close(ctx, executionId, "cr", request);
        assertEquals(200, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        JsonNode envelope = JSON.readTree(replay.getResponse().getContentAsString());
        assertTrue(envelope.path("meta").path("replayed").asBoolean());
        assertTrue(envelope.path("data").path("closed").asBoolean());
        assertEquals(closedAtBefore, envelope.path("data").path("closedAt").asText());
        assertEquals(manifestBefore, executionRow(executionId).get("manifest"));
    }

    @Test
    @DisplayName("A06 已 closed 新键 → 409 already_closed")
    void a06AlreadyClosed() throws Exception {
        Ctx ctx = newCtx("inst-a06-closed");
        UUID executionId = stoppedExecution(ctx, "inst-a06-closed", "stopped");
        seedRecords(ctx, executionId, 1, 2, 3);
        close(ctx, executionId, "ca1", body("5", "user_finished", "epoch-1", "3", "3"));
        MvcResult again = close(ctx, executionId, "ca2", body("5", "user_finished", "epoch-1", "3", "3"));
        assertEquals(409, again.getResponse().getStatus());
        assertEquals("EXECUTION_NOT_RESUMABLE", error(again).path("code").asText());
        assertEquals("already_closed", error(again).path("details").path("reason").asText());
    }

    @Test
    @DisplayName("A06 非原控制端 404 与不存在 id 全等；撤销授权 APP 原控制端仍可收尾")
    void a06VisibilityAndRevokedGrant() throws Exception {
        Ctx ctx = newCtx("inst-a06-owner");
        UUID executionId = stoppedExecution(ctx, "inst-a06-owner", "stopped");
        seedRecords(ctx, executionId, 1, 2, 3);
        String request = body("5", "user_finished", "epoch-1", "3", "3");

        String phone = jdbc.queryForObject("SELECT login_subject FROM accounts WHERE id = ?",
                String.class, UUID.fromString(ctx.login().accountId()));
        LoginResult otherInstall = loginAppWithInstallation(phone, "inst-a06-other");
        MvcResult wrong = CareAdmissionTestSupport.postJson(mockMvc, otherInstall.accessToken(),
                "/api/v1/care-executions/" + executionId + "/closure-confirmations", "co1", request);
        assertEquals(404, wrong.getResponse().getStatus());
        MvcResult missing = CareAdmissionTestSupport.postJson(mockMvc, otherInstall.accessToken(),
                "/api/v1/care-executions/" + UUID.randomUUID() + "/closure-confirmations", "co2", request);
        assertEquals(404, missing.getResponse().getStatus());
        assertEquals(CareTestFixtures.errorTree(wrong), CareTestFixtures.errorTree(missing));

        // C-11：撤销授权后 APP 原控制端仍可收尾
        fx.revokeGrant(UUID.fromString(ctx.login().accountId()), ctx.memberId());
        MvcResult revoked = close(ctx, executionId, "co3", request);
        assertEquals(200, revoked.getResponse().getStatus(), revoked.getResponse().getContentAsString());
        assertTrue(data(revoked).path("closed").asBoolean());
    }

    @Test
    @DisplayName("A06 reason 空白 → 400")
    void a06BlankReason() throws Exception {
        Ctx ctx = newCtx("inst-a06-blank");
        UUID executionId = stoppedExecution(ctx, "inst-a06-blank", "stopped");
        MvcResult r = close(ctx, executionId, "cb", body("5", "   ", "epoch-1", "0", "0"));
        assertEquals(400, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(r).path("code").asText());
    }

    // ---------------- F5 / F6 / N1 ----------------

    @Test
    @DisplayName("F5 缺口不溢出：无记录 W=MAX → ranges=[{1,MAX}] 无负数")
    void f5AllMissingAtMaxW() throws Exception {
        Ctx ctx = newCtx("inst-f5-max");
        UUID executionId = stoppedExecution(ctx, "inst-f5-max", "stopped");
        String max = Long.toString(Long.MAX_VALUE);
        MvcResult r = close(ctx, executionId, "cf5a", body("5", "user_finished", "epoch-1", max, "0"));
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("gaps", error(r).path("details").path("reason").asText());
        JsonNode ranges = error(r).path("details").path("missingRanges");
        assertEquals(1, ranges.size());
        assertEquals("1", ranges.get(0).path("from").asText());
        assertEquals(max, ranges.get(0).path("to").asText());
    }

    @Test
    @DisplayName("F5 记录仅 seq=MAX、W=MAX → ranges=[{1,MAX-1}]（无 W+1 溢出）")
    void f5SingleMaxSeqRecord() throws Exception {
        Ctx ctx = newCtx("inst-f5-single");
        UUID executionId = stoppedExecution(ctx, "inst-f5-single", "stopped");
        fx.seedRecord(executionId, ctx.planId(), ctx.memberId(), ctx.micro(), "rmax", "epoch-1",
                Long.MAX_VALUE, 1);
        String max = Long.toString(Long.MAX_VALUE);
        MvcResult r = close(ctx, executionId, "cf5b", body("5", "user_finished", "epoch-1", max, "1"));
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("gaps", error(r).path("details").path("reason").asText());
        JsonNode ranges = error(r).path("details").path("missingRanges");
        assertEquals(1, ranges.size());
        assertEquals("1", ranges.get(0).path("from").asText());
        assertEquals(Long.toString(Long.MAX_VALUE - 1), ranges.get(0).path("to").asText());
    }

    @Test
    @DisplayName("F6 A06 长 reason（300 字符）不因长度 400（错误 stopSeq → 409）")
    void f6LongReasonNotLengthRejected() throws Exception {
        Ctx ctx = newCtx("inst-f6-long-reason");
        UUID executionId = stoppedExecution(ctx, "inst-f6-long-reason", "stopped");
        String longReason = "r".repeat(300);
        MvcResult r = close(ctx, executionId, "cf6", body("4", longReason, "epoch-1", "0", "0"));
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("STOP_NOT_CONFIRMED", error(r).path("code").asText());
    }

    @Test
    @DisplayName("N1 迟到差异留痕：closed 后迟到记录累计 late_variance，status/manifest 其余不变")
    void n1LateVarianceTrace() throws Exception {
        Ctx ctx = newCtx("inst-n1");
        UUID executionId = stoppedExecution(ctx, "inst-n1", "stopped");
        seedRecords(ctx, executionId, 1, 2, 3);
        MvcResult closed = close(ctx, executionId, "cn1", body("5", "user_finished", "epoch-1", "3", "3"));
        assertEquals(200, closed.getResponse().getStatus(), closed.getResponse().getContentAsString());
        String manifestBefore = (String) executionRow(executionId).get("manifest");

        MvcResult late1 = sync(ctx, executionId, "cn1a",
                syncBody(null, List.of(recordJson("late4", "epoch-1", "4", "1", "2026-09-10T04:00:04Z"))));
        assertEquals(200, late1.getResponse().getStatus(), late1.getResponse().getContentAsString());
        JsonNode manifest1 = JSON.readTree((String) executionRow(executionId).get("manifest"));
        assertEquals(1, manifest1.path("late_variance").path("late_records_count").asInt());
        assertEquals("4", manifest1.path("late_variance").path("late_max_source_seq").asText());
        assertEquals("closed", executionRow(executionId).get("status"));
        assertEquals(1L, ((Number) jdbc.queryForObject(
                "SELECT completed_count FROM care_plans WHERE id = ?", Long.class, ctx.planId()))
                .longValue());

        MvcResult late2 = sync(ctx, executionId, "cn1b",
                syncBody(null, List.of(
                        recordJson("late5", "epoch-1", "5", "1", "2026-09-10T04:00:05Z"),
                        recordJson("late6", "epoch-1", "6", "1", "2026-09-10T04:00:06Z"))));
        assertEquals(200, late2.getResponse().getStatus(), late2.getResponse().getContentAsString());
        JsonNode manifest2 = JSON.readTree((String) executionRow(executionId).get("manifest"));
        assertEquals(3, manifest2.path("late_variance").path("late_records_count").asInt());
        assertEquals("6", manifest2.path("late_variance").path("late_max_source_seq").asText());
        // 原 manifest 字段仍在（schema_version/record_stream_epoch/final_record_seq）
        assertEquals(manifest1.path("record_stream_epoch").asText(),
                manifest2.path("record_stream_epoch").asText());
        assertEquals(manifest1.path("final_record_seq").asText(),
                manifest2.path("final_record_seq").asText());
        assertTrue(manifestBefore.contains("schema_version"));
    }
}

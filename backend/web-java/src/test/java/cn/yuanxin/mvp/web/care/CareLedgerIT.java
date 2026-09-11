package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.observationJson;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.recordJson;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.syncBody;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** M4-A05 次数账本集成测试（真实 PG；锁外核验 + 锁内判重/汇总/观察合并 + T13 重放）。 */
class CareLedgerIT extends AbstractWebIT {

    private static final String CAPABILITIES = "{\"schema_version\":1,\"revision\":\"1\"}";
    private static final String T1 = "2026-09-10T04:00:01Z";
    private static final String T2 = "2026-09-10T04:00:02Z";
    private static final String T3 = "2026-09-10T04:00:03Z";
    private static final String T4 = "2026-09-10T04:00:04Z";
    private static final String T5 = "2026-09-10T04:00:05Z";
    private static final String T6 = "2026-09-10T04:00:06Z";

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private record Ctx(LoginResult login, UUID memberId, UUID planId, UUID micro, UUID assessment) {
    }

    private Ctx newCtx(String inst, long target, long completed) throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), inst);
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("ledger-g-" + UUID.randomUUID(), 1);
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, target, completed, 0, null);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);
        return new Ctx(login, memberId, planId, micro, assessment);
    }

    private UUID execution(Ctx ctx, String inst, String status, String epoch, Long lastSeq,
                           String latestObservation) {
        return execution(ctx, inst, status, epoch, lastSeq, latestObservation, ctx.micro());
    }

    private UUID execution(Ctx ctx, String inst, String status, String epoch, Long lastSeq,
                           String latestObservation, UUID micro) {
        var builder = fx.execution(ctx.planId(), ctx.memberId(), micro, ctx.assessment())
                .controllerApp(UUID.fromString(ctx.login().accountId()), inst)
                .status(status);
        if (lastSeq == null) {
            builder.observationEpoch(epoch);
        } else {
            builder.observation(epoch, lastSeq, latestObservation);
        }
        return builder.insert();
    }

    private MvcResult sync(Ctx ctx, String inst, UUID executionId, String key, String body)
            throws Exception {
        return CareAdmissionTestSupport.postJson(mockMvc, ctx.login().accessToken(),
                "/api/v1/care-executions/" + executionId + "/observations", key, body);
    }

    private static JsonNode data(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("data");
    }

    private static JsonNode error(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error");
    }

    private Map<String, Object> planRow(UUID planId) {
        return jdbc.queryForMap("SELECT completed_count, progress_revision FROM care_plans WHERE id = ?",
                planId);
    }

    private Map<String, Object> executionRow(UUID executionId) {
        return jdbc.queryForMap("SELECT status, accepted_count, last_observation_seq,"
                + " latest_observation::text AS latest_observation, closure_manifest::text AS manifest"
                + " FROM care_executions WHERE id = ?", executionId);
    }

    private int recordCount(UUID executionId) {
        return jdbc.queryForObject("SELECT count(*) FROM care_records WHERE execution_id = ?",
                Integer.class, executionId);
    }

    private static String acksDispositions(JsonNode d) {
        List<String> out = new ArrayList<>();
        for (JsonNode ack : d.path("acknowledgedRecords")) {
            out.add(ack.path("recordId").asText() + ":" + ack.path("disposition").asText());
        }
        return String.join(",", out);
    }

    // ---------------- basics ----------------

    @Test
    @DisplayName("A05 快乐批 3 记录+running 观察：accepted×3、K=3、progress、T08/T06/T07 落账")
    void a05HappyBatch() throws Exception {
        Ctx ctx = newCtx("inst-a05-happy", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-happy", "admitted", "epoch-1", null, null);
        String body = syncBody(observationJson("epoch-1", "1", "running", T1, null, null),
                List.of(recordJson("r1", "epoch-1", "1", "1", T1),
                        recordJson("r2", "epoch-1", "2", "1", T2),
                        recordJson("r3", "epoch-1", "3", "1", T3)));
        MvcResult r = sync(ctx, "inst-a05-happy", executionId, "k1", body);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        JsonNode d = data(r);
        assertEquals(3, d.path("acknowledgedRecords").size());
        assertEquals("running", d.path("executionStatus").asText());
        assertEquals("3", d.path("acceptedCount").asText());
        assertEquals("10", d.path("progress").path("targetCount").asText());
        assertEquals("3", d.path("progress").path("completedCount").asText());
        assertEquals("7", d.path("progress").path("remainingCount").asText());

        assertEquals(3, recordCount(executionId));
        assertEquals(3L, ((Number) planRow(ctx.planId()).get("completed_count")).longValue());
        assertEquals(1L, ((Number) planRow(ctx.planId()).get("progress_revision")).longValue());
        Map<String, Object> exec = executionRow(executionId);
        assertEquals("running", exec.get("status"));
        assertEquals(3L, ((Number) exec.get("accepted_count")).longValue());
        assertEquals(1L, ((Number) exec.get("last_observation_seq")).longValue());
        assertEquals(3, jdbc.queryForObject("SELECT count(*) FROM care_records WHERE execution_id = ?"
                + " AND payload->>'schema_version' IS NOT NULL", Integer.class, executionId));
        assertEquals(ctx.memberId(), jdbc.queryForObject(
                "SELECT member_id FROM care_records WHERE execution_id = ? AND client_record_id = 'r1'",
                UUID.class, executionId));
        assertEquals(ctx.micro(), jdbc.queryForObject(
                "SELECT microcrystal_id FROM care_records WHERE execution_id = ? AND client_record_id = 'r1'",
                UUID.class, executionId));
    }

    @Test
    @DisplayName("A05 同内容新键重传 duplicate×3：K/progress_revision/accepted_count 不变")
    void a05DuplicateRetransmit() throws Exception {
        Ctx ctx = newCtx("inst-a05-dup", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-dup", "admitted", "epoch-1", null, null);
        String body = syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "1", T1),
                recordJson("r2", "epoch-1", "2", "1", T2)));
        sync(ctx, "inst-a05-dup", executionId, "kd1", body);
        Map<String, Object> planBefore = planRow(ctx.planId());

        MvcResult r = sync(ctx, "inst-a05-dup", executionId, "kd2", body);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("r1:duplicate,r2:duplicate", acksDispositions(data(r)));
        assertEquals(planBefore, planRow(ctx.planId()));
        assertEquals(2L, ((Number) executionRow(executionId).get("accepted_count")).longValue());
        assertEquals(2, recordCount(executionId));
    }

    @Test
    @DisplayName("A05 同键重放 meta.replayed + 冻结 acks + 当前状态字段")
    void a05Replay() throws Exception {
        Ctx ctx = newCtx("inst-a05-replay", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-replay", "admitted", "epoch-1", null, null);
        String body = syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "1", T1)));
        sync(ctx, "inst-a05-replay", executionId, "kr", body);
        MvcResult replay = sync(ctx, "inst-a05-replay", executionId, "kr", body);
        assertEquals(200, replay.getResponse().getStatus());
        JsonNode envelope = JSON.readTree(replay.getResponse().getContentAsString());
        assertTrue(envelope.path("meta").path("replayed").asBoolean());
        assertEquals("r1:accepted", acksDispositions(envelope.path("data")));
        assertEquals("1", envelope.path("data").path("acceptedCount").asText());
    }

    @Test
    @DisplayName("A05 批内完全重复折叠 accepted+duplicate，K 只加一次")
    void a05BatchInternalFold() throws Exception {
        Ctx ctx = newCtx("inst-a05-fold", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-fold", "admitted", "epoch-1", null, null);
        String record = recordJson("r1", "epoch-1", "1", "1", T1);
        MvcResult r = sync(ctx, "inst-a05-fold", executionId, "kf", syncBody(null, List.of(record, record)));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("r1:accepted,r1:duplicate", acksDispositions(data(r)));
        assertEquals(1L, ((Number) planRow(ctx.planId()).get("completed_count")).longValue());
        assertEquals(1, recordCount(executionId));
    }

    @Test
    @DisplayName("A05 批内同 recordId 异内容 / 同 (epoch,seq) 异 recordId → 409 整批回滚")
    void a05BatchConflicts() throws Exception {
        Ctx ctx = newCtx("inst-a05-bconf", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-bconf", "admitted", "epoch-1", null, null);

        MvcResult sameId = sync(ctx, "inst-a05-bconf", executionId, "kb1",
                syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "1", T1),
                        recordJson("r1", "epoch-1", "1", "2", T1))));
        assertEquals(409, sameId.getResponse().getStatus());
        assertEquals("RECORD_CONFLICT", error(sameId).path("code").asText());

        MvcResult sameSeq = sync(ctx, "inst-a05-bconf", executionId, "kb2",
                syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "1", T1),
                        recordJson("r2", "epoch-1", "1", "1", T2))));
        assertEquals(409, sameSeq.getResponse().getStatus());
        assertEquals("RECORD_CONFLICT", error(sameSeq).path("code").asText());
        assertEquals(0, recordCount(executionId));
        assertEquals(0L, ((Number) planRow(ctx.planId()).get("completed_count")).longValue());
    }

    @Test
    @DisplayName("A05 DB 冲突：复用 recordId 异内容 / 换 recordId 复用 seq → 409（双键独立识别）")
    void a05DbConflicts() throws Exception {
        Ctx ctx = newCtx("inst-a05-dbconf", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-dbconf", "admitted", "epoch-1", null, null);
        sync(ctx, "inst-a05-dbconf", executionId, "kd1",
                syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "1", T1))));

        MvcResult sameId = sync(ctx, "inst-a05-dbconf", executionId, "kd2",
                syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "2", T1))));
        assertEquals(409, sameId.getResponse().getStatus());
        assertTrue(error(sameId).path("details").path("conflictingRecordIds").toString().contains("r1"));

        MvcResult sameSeq = sync(ctx, "inst-a05-dbconf", executionId, "kd3",
                syncBody(null, List.of(recordJson("r2", "epoch-1", "1", "1", T2))));
        assertEquals(409, sameSeq.getResponse().getStatus());
        assertEquals("RECORD_CONFLICT", error(sameSeq).path("code").asText());
        assertEquals(1, recordCount(executionId));
    }

    @Test
    @DisplayName("A05 epoch 不符记录逐条 rejected epoch_mismatch，其余 accepted，K 只计 accepted")
    void a05RecordEpochMismatch() throws Exception {
        Ctx ctx = newCtx("inst-a05-ep", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-ep", "admitted", "epoch-1", null, null);
        MvcResult r = sync(ctx, "inst-a05-ep", executionId, "kep",
                syncBody(null, List.of(recordJson("bad", "other-epoch", "1", "1", T1),
                        recordJson("good", "epoch-1", "2", "1", T2))));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertEquals("rejected", d.path("acknowledgedRecords").get(0).path("disposition").asText());
        assertEquals("epoch_mismatch",
                d.path("acknowledgedRecords").get(0).path("rejectReason").asText());
        assertEquals("accepted", d.path("acknowledgedRecords").get(1).path("disposition").asText());
        assertEquals("1", d.path("acceptedCount").asText());
        assertEquals(1, recordCount(executionId));
    }

    @Test
    @DisplayName("A05 observation epoch 不符 → 409 整批（记录不入账）")
    void a05ObservationEpochMismatch() throws Exception {
        Ctx ctx = newCtx("inst-a05-oep", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-oep", "admitted", "epoch-1", null, null);
        MvcResult r = sync(ctx, "inst-a05-oep", executionId, "koep",
                syncBody(observationJson("other", "1", "running", T1, null, null),
                        List.of(recordJson("r1", "epoch-1", "1", "1", T1))));
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("RECORD_CONFLICT", error(r).path("code").asText());
        assertEquals("observation_epoch_mismatch", error(r).path("details").path("reason").asText());
        assertEquals(0, recordCount(executionId));
    }

    @Test
    @DisplayName("A05 旧 seq 忽略、同 seq 同内容忽略、同 seq 异内容 409")
    void a05ObservationSeqRules() throws Exception {
        Ctx ctx = newCtx("inst-a05-seq", 10, 0);
        String stored = "{\"schema_version\":1,\"epoch\":\"epoch-1\",\"seq\":\"2\","
                + "\"state\":\"running\",\"occurred_at\":\"" + T2 + "\","
                + "\"continuity_invalidated\":false}";
        UUID executionId = execution(ctx, "inst-a05-seq", "running", "epoch-1", 2L, stored);

        MvcResult older = sync(ctx, "inst-a05-seq", executionId, "ks1",
                syncBody(observationJson("epoch-1", "1", "running", T1, null, null),
                        List.of(recordJson("r1", "epoch-1", "1", "1", T1))));
        assertEquals(200, older.getResponse().getStatus(), older.getResponse().getContentAsString());
        assertEquals(2L, ((Number) executionRow(executionId).get("last_observation_seq")).longValue());

        MvcResult same = sync(ctx, "inst-a05-seq", executionId, "ks2",
                syncBody(observationJson("epoch-1", "2", "running", T2, null, null), List.of()));
        assertEquals(200, same.getResponse().getStatus(), same.getResponse().getContentAsString());

        MvcResult conflict = sync(ctx, "inst-a05-seq", executionId, "ks3",
                syncBody(observationJson("epoch-1", "2", "paused", T2, null, null), List.of()));
        assertEquals(409, conflict.getResponse().getStatus());
        assertEquals("observation_seq_conflict", error(conflict).path("details").path("reason").asText());
    }

    @Test
    @DisplayName("A05 状态机：continuity 失效 paused 收 running→仍 paused；A04 清除后→running")
    void a05RunningGate() throws Exception {
        Ctx ctx = newCtx("inst-a05-gate", 10, 0);
        String invalidated = "{\"schema_version\":1,\"epoch\":\"epoch-1\",\"seq\":\"1\","
                + "\"state\":\"paused\",\"occurred_at\":\"" + T1 + "\","
                + "\"verification_revision\":\"1\",\"continuity_valid\":false,"
                + "\"continuity_invalidated\":true}";
        UUID blocked = execution(ctx, "inst-a05-gate", "paused", "epoch-1", 1L, invalidated);
        sync(ctx, "inst-a05-gate", blocked, "kg1",
                syncBody(observationJson("epoch-1", "2", "running", T2, "1", true), List.of()));
        Map<String, Object> blockedRow = executionRow(blocked);
        assertEquals("paused", blockedRow.get("status"));
        assertEquals(2L, ((Number) blockedRow.get("last_observation_seq")).longValue());
        assertTrue(((String) blockedRow.get("latest_observation")).contains("\"state\": \"running\"")
                || ((String) blockedRow.get("latest_observation")).contains("\"state\":\"running\""));
        assertTrue(((String) blockedRow.get("latest_observation")).contains("true"));

        String cleared = "{\"schema_version\":1,\"epoch\":\"epoch-1\",\"seq\":\"1\","
                + "\"state\":\"paused\",\"occurred_at\":\"" + T1 + "\","
                + "\"verification_revision\":\"2\",\"continuity_valid\":false,"
                + "\"continuity_invalidated\":false}";
        UUID allowedExecution = execution(ctx, "inst-a05-gate", "paused", "epoch-1", 1L, cleared,
                fx.seedMicrocrystal(CAPABILITIES));
        jdbc.update("UPDATE care_executions SET verification_revision=2 WHERE id=?", allowedExecution);
        sync(ctx, "inst-a05-gate", allowedExecution, "kg2",
                syncBody(observationJson("epoch-1", "2", "running", T2, "2", true), List.of()));
        assertEquals("running", executionRow(allowedExecution).get("status"));
    }

    @Test
    @DisplayName("A05 状态机：unknown 收 running 不变、paused→paused、stopped→stopped+stopped_at")
    void a05UnknownTransitions() throws Exception {
        Ctx ctx = newCtx("inst-a05-unk", 10, 0);
        String unknownObs = "{\"schema_version\":1,\"epoch\":\"epoch-1\",\"seq\":\"1\","
                + "\"state\":\"unknown\",\"occurred_at\":\"" + T1 + "\","
                + "\"continuity_invalidated\":false}";
        UUID executionId = execution(ctx, "inst-a05-unk", "unknown", "epoch-1", 1L, unknownObs);

        sync(ctx, "inst-a05-unk", executionId, "ku1",
                syncBody(observationJson("epoch-1", "2", "running", T2, null, null), List.of()));
        assertEquals("unknown", executionRow(executionId).get("status"));

        sync(ctx, "inst-a05-unk", executionId, "ku2",
                syncBody(observationJson("epoch-1", "3", "paused", T3, null, null), List.of()));
        assertEquals("paused", executionRow(executionId).get("status"));

        sync(ctx, "inst-a05-unk", executionId, "ku3",
                syncBody(observationJson("epoch-1", "4", "stopped", T4, null, null), List.of()));
        Map<String, Object> row = executionRow(executionId);
        assertEquals("stopped", row.get("status"));
        assertNotNull(jdbc.queryForObject("SELECT stopped_at FROM care_executions WHERE id = ?",
                java.sql.Timestamp.class, executionId));
    }

    @Test
    @DisplayName("A05 stopped 收高 seq running：状态/观察列冻结、记录仍入账")
    void a05StoppedFreeze() throws Exception {
        Ctx ctx = newCtx("inst-a05-freeze", 10, 0);
        String stoppedObs = "{\"schema_version\":1,\"epoch\":\"epoch-1\",\"seq\":\"5\","
                + "\"state\":\"stopped\",\"occurred_at\":\"" + T5 + "\","
                + "\"continuity_invalidated\":false}";
        UUID executionId = execution(ctx, "inst-a05-freeze", "stopped", "epoch-1", 5L, stoppedObs);
        Map<String, Object> before = executionRow(executionId);

        MvcResult r = sync(ctx, "inst-a05-freeze", executionId, "kz1",
                syncBody(observationJson("epoch-1", "6", "running", T6, null, null),
                        List.of(recordJson("late", "epoch-1", "1", "1", T6))));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        Map<String, Object> after = executionRow(executionId);
        assertEquals("stopped", after.get("status"));
        assertEquals(before.get("last_observation_seq"), after.get("last_observation_seq"));
        assertEquals(before.get("latest_observation"), after.get("latest_observation"));
        assertEquals(1L, ((Number) after.get("accepted_count")).longValue());
        assertEquals(1, recordCount(executionId));
    }

    @Test
    @DisplayName("A05 closed 收记录：K/accepted_count 增、status 仍 closed、N1 留 late_variance")
    void a05ClosedLateRecord() throws Exception {
        Ctx ctx = newCtx("inst-a05-closed", 10, 0);
        String stoppedObs = "{\"schema_version\":1,\"epoch\":\"epoch-1\",\"seq\":\"5\","
                + "\"state\":\"stopped\",\"occurred_at\":\"" + T5 + "\","
                + "\"continuity_invalidated\":false}";
        UUID executionId = execution(ctx, "inst-a05-closed", "stopped", "epoch-1", 5L, stoppedObs);
        jdbc.update("UPDATE care_executions SET status='closed', closed_at=now() WHERE id=?",
                executionId);

        MvcResult r = sync(ctx, "inst-a05-closed", executionId, "kcl",
                syncBody(null, List.of(recordJson("late", "epoch-1", "1", "1", T6))));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("closed", executionRow(executionId).get("status"));
        assertEquals(1L, ((Number) executionRow(executionId).get("accepted_count")).longValue());
        JsonNode manifest = JSON.readTree((String) executionRow(executionId).get("manifest"));
        assertEquals(1, manifest.path("late_variance").path("late_records_count").asInt());
        assertEquals("1", manifest.path("late_variance").path("late_max_source_seq").asText());
        assertEquals(1L, ((Number) planRow(ctx.planId()).get("completed_count")).longValue());
    }

    @Test
    @DisplayName("A05 K 边界：9→10 完成、迟到 11 不截断、之后 A03 409 PLAN_COMPLETED")
    void a05KBoundary() throws Exception {
        Ctx ctx = newCtx("inst-a05-k", 10, 9);
        UUID executionId = execution(ctx, "inst-a05-k", "running", "epoch-1", null, null);
        sync(ctx, "inst-a05-k", executionId, "kk1",
                syncBody(null, List.of(recordJson("r10", "epoch-1", "1", "1", T1))));
        Map<String, Object> plan = jdbc.queryForMap("SELECT completed_count, progress_revision,"
                + " completed_at FROM care_plans WHERE id = ?", ctx.planId());
        assertEquals(10L, ((Number) plan.get("completed_count")).longValue());
        Object firstCompletedAt = plan.get("completed_at");
        assertNotNull(firstCompletedAt);
        MvcResult progress = mockMvc.perform(org.springframework.test.web.servlet.request
                        .MockMvcRequestBuilders.get("/api/v1/care-plans/" + ctx.planId() + "/progress")
                        .header("Authorization", "Bearer " + ctx.login().accessToken()))
                .andReturn();
        JsonNode pd = JSON.readTree(progress.getResponse().getContentAsString()).path("data");
        assertTrue(pd.path("isCompleted").asBoolean());
        assertEquals("0", pd.path("remainingCount").asText());

        sync(ctx, "inst-a05-k", executionId, "kk2",
                syncBody(null, List.of(recordJson("r11", "epoch-1", "2", "1", T2))));
        Map<String, Object> planAfter = jdbc.queryForMap("SELECT completed_count, completed_at"
                + " FROM care_plans WHERE id = ?", ctx.planId());
        assertEquals(11L, ((Number) planAfter.get("completed_count")).longValue());
        assertEquals(firstCompletedAt, planAfter.get("completed_at"));

        MvcResult admission = CareAdmissionTestSupport.admit(mockMvc, ctx.login().accessToken(),
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(ctx.micro(), "p", ctx.planId(), null, null,
                        CareAdmissionTestSupport.capture("c", T1, "cc", "admission"), "consent"),
                CareAdmissionTestSupport.PNG);
        assertEquals(409, admission.getResponse().getStatus());
        assertEquals("PLAN_COMPLETED",
                JSON.readTree(admission.getResponse().getContentAsString()).path("error").path("code").asText());
    }

    @Test
    @DisplayName("A05 插入后回滚：方案非 ready → 500 且 T08/T07 计数不变")
    void a05LedgerRollback() throws Exception {
        Ctx ctx = newCtx("inst-a05-rollback", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-rollback", "admitted", "epoch-1", null, null);
        jdbc.update("UPDATE care_plans SET generation_status='generating' WHERE id=?", ctx.planId());

        MvcResult r = sync(ctx, "inst-a05-rollback", executionId, "krb",
                syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "1", T1))));
        assertEquals(500, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("INTERNAL", error(r).path("code").asText());
        assertEquals(0, recordCount(executionId));
        assertEquals(0L, ((Number) executionRow(executionId).get("accepted_count")).longValue());
    }

    @Test
    @DisplayName("A05 撤销授权 APP 原控制端：记录入账、acks 正常、progress null")
    void a05RevokedGrantMinimalAck() throws Exception {
        Ctx ctx = newCtx("inst-a05-revoked", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-revoked", "admitted", "epoch-1", null, null);
        fx.revokeGrant(UUID.fromString(ctx.login().accountId()), ctx.memberId());

        MvcResult r = sync(ctx, "inst-a05-revoked", executionId, "krv",
                syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "1", T1))));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertEquals("r1:accepted", acksDispositions(d));
        assertTrue(d.path("progress").isNull());
        assertEquals("1", d.path("acceptedCount").asText());
    }

    @Test
    @DisplayName("A05 云台控制端：progress 附带")
    void a05GimbalProgress() throws Exception {
        UUID gimbalId = fx.seedGimbal("a05-gimbal-login-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 10, 0, 0, null);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID executionId = fx.execution(planId, memberId, micro, assessment)
                .controllerGimbal(gimbalId).status("admitted").observationEpoch("epoch-g").insert();

        MvcResult r = CareAdmissionTestSupport.postJson(mockMvc, token,
                "/api/v1/care-executions/" + executionId + "/observations", "kg",
                syncBody(null, List.of(recordJson("r1", "epoch-g", "1", "1", T1))));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertFalse(d.path("progress").isNull());
        assertEquals("1", d.path("progress").path("completedCount").asText());
    }

    @Test
    @DisplayName("A05 非原控制端（换安装）404 与不存在 id 全等")
    void a05NonControllerNotFoundEqual() throws Exception {
        Ctx ctx = newCtx("inst-a05-owner", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-owner", "admitted", "epoch-1", null, null);
        String phone = jdbc.queryForObject("SELECT login_subject FROM accounts WHERE id = ?",
                String.class, UUID.fromString(ctx.login().accountId()));
        LoginResult otherInstall = loginAppWithInstallation(phone, "inst-a05-other");
        String body = syncBody(null, List.of());

        MvcResult wrong = CareAdmissionTestSupport.postJson(mockMvc, otherInstall.accessToken(),
                "/api/v1/care-executions/" + executionId + "/observations", "k1", body);
        assertEquals(404, wrong.getResponse().getStatus());
        MvcResult missing = CareAdmissionTestSupport.postJson(mockMvc, otherInstall.accessToken(),
                "/api/v1/care-executions/" + UUID.randomUUID() + "/observations", "k2", body);
        assertEquals(404, missing.getResponse().getStatus());
        assertEquals(CareTestFixtures.errorTree(wrong), CareTestFixtures.errorTree(missing));
    }

    @Test
    @DisplayName("A05 delta 溢出 → 400 count_overflow 且不入账")
    void a05CountOverflow() throws Exception {
        Ctx ctx = newCtx("inst-a05-overflow", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-overflow", "admitted", "epoch-1", null, null);
        String max = "9223372036854775807";
        MvcResult r = sync(ctx, "inst-a05-overflow", executionId, "kov",
                syncBody(null, List.of(recordJson("a", "epoch-1", "1", max, T1),
                        recordJson("b", "epoch-1", "2", max, T2))));
        assertEquals(400, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("count_overflow", error(r).path("details").path("reason").asText());
        assertEquals(0, recordCount(executionId));
    }

    @Test
    @DisplayName("A05 仅 observation 无记录 / 空批无观察 no-op")
    void a05ObservationOnlyAndEmptyNoop() throws Exception {
        Ctx ctx = newCtx("inst-a05-empty", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-empty", "admitted", "epoch-1", null, null);

        MvcResult obsOnly = sync(ctx, "inst-a05-empty", executionId, "ko1",
                syncBody(observationJson("epoch-1", "1", "paused", T1, null, null), List.of()));
        assertEquals(200, obsOnly.getResponse().getStatus(), obsOnly.getResponse().getContentAsString());
        assertEquals(0, data(obsOnly).path("acknowledgedRecords").size());
        assertEquals("paused", data(obsOnly).path("executionStatus").asText());

        MvcResult empty = sync(ctx, "inst-a05-empty", executionId, "ko2", syncBody(null, List.of()));
        assertEquals(200, empty.getResponse().getStatus(), empty.getResponse().getContentAsString());
        assertEquals(0, data(empty).path("acknowledgedRecords").size());
        assertEquals(0L, ((Number) planRow(ctx.planId()).get("progress_revision")).longValue());
        assertEquals(0L, ((Number) executionRow(executionId).get("accepted_count")).longValue());
    }

    @Test
    @DisplayName("A05 201 条记录 → 400；缺 Idempotency-Key → 400")
    void a05LimitsAndMissingKey() throws Exception {
        Ctx ctx = newCtx("inst-a05-limits", 10, 0);
        UUID executionId = execution(ctx, "inst-a05-limits", "admitted", "epoch-1", null, null);
        List<String> records = new ArrayList<>();
        for (int i = 1; i <= 201; i++) {
            records.add(recordJson("r" + i, "epoch-1", Integer.toString(i), "1", T1));
        }
        MvcResult tooMany = sync(ctx, "inst-a05-limits", executionId, "klim",
                syncBody(null, records));
        assertEquals(400, tooMany.getResponse().getStatus());

        MvcResult missingKey = sync(ctx, "inst-a05-limits", executionId, null, syncBody(null, List.of()));
        assertEquals(400, missingKey.getResponse().getStatus());
        assertEquals("INVALID_INPUT", error(missingKey).path("code").asText());
    }

    // ---------------- F4 / F1 / F6 ----------------

    @Test
    @DisplayName("F4 admitted→running 统一门控：失效/代次不符→仍 admitted，满足→running")
    void f4AdmittedRunningGate() throws Exception {
        Ctx ctx = newCtx("inst-f4-gate", 10, 0);
        UUID blocked = execution(ctx, "inst-f4-gate", "admitted", "epoch-1", null, null,
                fx.seedMicrocrystal(CAPABILITIES));
        sync(ctx, "inst-f4-gate", blocked, "kf41",
                syncBody(observationJson("epoch-1", "1", "running", T1, null, false), List.of()));
        Map<String, Object> blockedRow = executionRow(blocked);
        assertEquals("admitted", blockedRow.get("status"));
        String blockedObservation = (String) blockedRow.get("latest_observation");
        assertTrue(blockedObservation.contains("\"continuity_invalidated\": true")
                || blockedObservation.contains("\"continuity_invalidated\":true"));

        UUID stale = execution(ctx, "inst-f4-gate", "admitted", "epoch-1", null, null,
                fx.seedMicrocrystal(CAPABILITIES));
        sync(ctx, "inst-f4-gate", stale, "kf42",
                syncBody(observationJson("epoch-1", "1", "running", T1, "999", null), List.of()));
        assertEquals("admitted", executionRow(stale).get("status"));

        UUID allowed = execution(ctx, "inst-f4-gate", "admitted", "epoch-1", null, null,
                fx.seedMicrocrystal(CAPABILITIES));
        sync(ctx, "inst-f4-gate", allowed, "kf43",
                syncBody(observationJson("epoch-1", "1", "running", T1, null, null), List.of()));
        assertEquals("running", executionRow(allowed).get("status"));
    }

    @Test
    @DisplayName("F1 A05 云台原控制端指针被换 → 200 最小确认且 progress=null")
    void f1GimbalProgressRequiresCurrentTask() throws Exception {
        UUID gimbalId = fx.seedGimbal("f1-a05-gimbal-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 10, 0, 0, null);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID executionId = fx.execution(planId, memberId, micro, assessment)
                .controllerGimbal(gimbalId).status("admitted").observationEpoch("epoch-g").insert();
        UUID otherAssessment = fx.seedAssessment(gimbalId, memberId);
        fx.pointGimbalAtAssessment(gimbalId, otherAssessment);

        MvcResult r = CareAdmissionTestSupport.postJson(mockMvc, token,
                "/api/v1/care-executions/" + executionId + "/observations", "kf1g",
                syncBody(null, List.of()));
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertTrue(d.path("progress").isNull());
        assertEquals("admitted", d.path("executionStatus").asText());
        assertEquals("0", d.path("acceptedCount").asText());
        assertEquals(0, d.path("acknowledgedRecords").size());
    }

    @Test
    @DisplayName("F6 records:[null] → 400 而非 500")
    void f6RecordsNullElement() throws Exception {
        Ctx ctx = newCtx("inst-f6-null-record", 10, 0);
        UUID executionId = execution(ctx, "inst-f6-null-record", "admitted", "epoch-1", null, null);
        MvcResult r = sync(ctx, "inst-f6-null-record", executionId, "kf6",
                syncBody(null, java.util.Collections.singletonList("null")));
        assertEquals(400, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(r).path("code").asText());
    }
}

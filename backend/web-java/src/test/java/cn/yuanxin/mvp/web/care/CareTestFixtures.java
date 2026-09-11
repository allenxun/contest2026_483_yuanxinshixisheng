package cn.yuanxin.mvp.web.care;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.time.Instant;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * M4 护理查询集成测试种子支撑：直连 SQL 建立 T13/T01/T02/T03/T04/T05/T06/T07/T08
 * 行，满足全部列 CHECK（JSONB 带 schema_version、控制端归属互斥、closed⇔closed_at 等）。
 * 以及云台设备登录 helper（POST /api/v1/gimbal-sessions）。
 */
public class CareTestFixtures {

    private static final ObjectMapper JSON = new ObjectMapper();

    private final JdbcTemplate jdbc;

    public CareTestFixtures(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // ---------- T13 / T01 / T02 ----------

    public UUID seedIdempotencyRequest() {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO idempotency_requests (id, principal_type, principal_id, operation,"
                        + " idempotency_key, payload_hash, status)"
                        + " VALUES (?, 'app_account', 'seed', 'seed', ?, 'seed', 'succeeded')",
                id, "seed-" + id);
        return id;
    }

    public UUID seedMember() {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO members (id) VALUES (?)", id);
        return id;
    }

    public UUID seedGrant(UUID accountId, UUID memberId, String status) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO member_access_grants (id, account_id, member_id, status, source_request_id)"
                        + " VALUES (?, ?, ?, ?, ?)",
                id, accountId, memberId, status, seedIdempotencyRequest());
        return id;
    }

    public void revokeGrant(UUID accountId, UUID memberId) {
        jdbc.update("UPDATE member_access_grants SET status='revoked', revoked_at=now(), updated_at=now()"
                + " WHERE account_id=? AND member_id=?", accountId, memberId);
    }

    // ---------- T03 / T04 / T05 ----------

    public UUID seedGimbal(String authSubjectRef, long credentialVersion) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                        + " VALUES (?, ?, ?, ?)",
                id, "gimbal-" + id, authSubjectRef, credentialVersion);
        return id;
    }

    public void pointGimbalAtAssessment(UUID gimbalId, UUID assessmentId) {
        jdbc.update("UPDATE gimbals SET current_assessment_id=?, current_assessment_revision=1,"
                + " updated_at=now() WHERE id=?", assessmentId, gimbalId);
    }

    public UUID seedMicrocrystal() {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO microcrystals (id, serial_no) VALUES (?, ?)",
                id, "mic-" + id);
        return id;
    }

    /** 带能力 JSON 的微晶（非空 capabilities 须带数字 schema_version，见 V1 CHECK）。 */
    public UUID seedMicrocrystal(String capabilitiesJson) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO microcrystals (id, serial_no, capabilities)"
                        + " VALUES (?, ?, CAST(? AS jsonb))",
                id, "mic-" + id, capabilitiesJson == null ? "{}" : capabilitiesJson);
        return id;
    }

    /** 普通评估行（非 report_ready）。 */
    public UUID seedAssessment(UUID gimbalId, UUID memberId) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO skin_assessments (id, gimbal_id, member_id, status, source_request_id)"
                        + " VALUES (?, ?, ?, 'queued', ?)",
                id, gimbalId, memberId, seedIdempotencyRequest());
        return id;
    }

    /** report_ready 评估行（带 report_id），供 A01 reportId 过滤定位。 */
    public UUID seedReportAssessment(UUID gimbalId, UUID memberId, UUID reportId) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO skin_assessments (id, gimbal_id, member_id, status, report_id,"
                        + " report_payload, report_photo_version, source_request_id)"
                        + " VALUES (?, ?, ?, 'report_ready', ?, CAST(? AS jsonb), 1, ?)",
                id, gimbalId, memberId, reportId, "{\"schema_version\":1}", seedIdempotencyRequest());
        return id;
    }

    // ---------- T06 ----------

    public UUID seedPlan(UUID assessmentId, UUID memberId, String generationStatus,
                         String planSummaryJson, String planPayloadJson, Long targetCount,
                         long completedCount, long progressRevision, Instant completedAt) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO care_plans (id, assessment_id, member_id, generation_status,"
                        + " plan_summary, plan_payload, target_count, completed_count,"
                        + " progress_revision, completed_at)"
                        + " VALUES (?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS jsonb), ?, ?, ?, ?)",
                id, assessmentId, memberId, generationStatus,
                planSummaryJson == null ? "{}" : planSummaryJson,
                planPayloadJson, targetCount, completedCount, progressRevision,
                completedAt == null ? null : java.sql.Timestamp.from(completedAt));
        return id;
    }

    public UUID seedWaitingPlan(UUID assessmentId, UUID memberId, String planSummaryJson) {
        return seedPlan(assessmentId, memberId, "waiting_inputs", planSummaryJson, null,
                null, 0, 0, null);
    }

    public UUID seedGeneratingPlan(UUID assessmentId, UUID memberId) {
        return seedPlan(assessmentId, memberId, "generating", "{\"schema_version\":1}", null,
                null, 0, 0, null);
    }

    public UUID seedFailedPlan(UUID assessmentId, UUID memberId, String internalFailureDetail) {
        UUID id = seedPlan(assessmentId, memberId, "failed", "{\"schema_version\":1}", null,
                null, 0, 0, null);
        jdbc.update("UPDATE care_plans SET failure_detail=CAST(? AS jsonb) WHERE id=?",
                internalFailureDetail, id);
        return id;
    }

    public UUID seedReadyPlan(UUID assessmentId, UUID memberId, long target, long completed,
                              long progressRevision, Instant completedAt) {
        return seedPlan(assessmentId, memberId, "ready",
                "{\"schema_version\":1,\"title\":\"摘要标题\"}",
                "{\"schema_version\":1,\"title\":\"完整方案\",\"steps\":[{\"order\":1}]}",
                target, completed, progressRevision, completedAt);
    }

    public void setPlanCreatedAt(UUID planId, Instant createdAt) {
        jdbc.update("UPDATE care_plans SET created_at=? WHERE id=?",
                java.sql.Timestamp.from(createdAt), planId);
    }

    /** 设置 T06 输入快照（如 required_capability_revision 能力覆盖校验）。 */
    public void setPlanInputSnapshot(UUID planId, String inputSnapshotJson) {
        jdbc.update("UPDATE care_plans SET input_snapshot=CAST(? AS jsonb) WHERE id=?",
                inputSnapshotJson, planId);
    }

    // ---------- T07 ----------

    public UUID seedAppExecution(UUID planId, UUID memberId, UUID microcrystalId,
                                 UUID assessmentIdAtStart, UUID accountId, String installationId) {
        return execution(planId, memberId, microcrystalId, assessmentIdAtStart)
                .controllerApp(accountId, installationId)
                .insert();
    }

    public UUID seedGimbalExecution(UUID planId, UUID memberId, UUID microcrystalId,
                                    UUID assessmentIdAtStart, UUID gimbalId) {
        return execution(planId, memberId, microcrystalId, assessmentIdAtStart)
                .controllerGimbal(gimbalId)
                .insert();
    }

    public ExecutionBuilder execution(UUID planId, UUID memberId, UUID microcrystalId,
                                      UUID assessmentIdAtStart) {
        return new ExecutionBuilder(planId, memberId, microcrystalId, assessmentIdAtStart);
    }

    /** 执行行建造器：字段默认合法，测试按需覆盖。 */
    public final class ExecutionBuilder {
        private final UUID planId;
        private final UUID memberId;
        private final UUID microcrystalId;
        private final UUID assessmentIdAtStart;
        private String controllerType = "app";
        private UUID controllerAccountId;
        private String controllerInstallationId;
        private UUID controllerGimbalId;
        private String status = "admitted";
        private long verificationRevision = 1;
        private String planSnapshot = "{}";
        private String observationEpoch;
        private Long lastObservationSeq;
        private String latestObservation;
        private long acceptedCount;
        private String latestVerification = "{}";
        private Instant lastVerifiedAt;
        private Instant stoppedAt;
        private Instant closedAt;
        private Instant createdAt;

        private ExecutionBuilder(UUID planId, UUID memberId, UUID microcrystalId,
                                 UUID assessmentIdAtStart) {
            this.planId = planId;
            this.memberId = memberId;
            this.microcrystalId = microcrystalId;
            this.assessmentIdAtStart = assessmentIdAtStart;
        }

        public ExecutionBuilder controllerApp(UUID accountId, String installationId) {
            this.controllerType = "app";
            this.controllerAccountId = accountId;
            this.controllerInstallationId = installationId;
            this.controllerGimbalId = null;
            return this;
        }

        public ExecutionBuilder controllerGimbal(UUID gimbalId) {
            this.controllerType = "gimbal";
            this.controllerGimbalId = gimbalId;
            this.controllerAccountId = null;
            this.controllerInstallationId = null;
            return this;
        }

        public ExecutionBuilder status(String value) {
            this.status = value;
            return this;
        }

        public ExecutionBuilder verificationRevision(long value) {
            this.verificationRevision = value;
            return this;
        }

        public ExecutionBuilder planSnapshot(String json) {
            this.planSnapshot = json;
            return this;
        }

        public ExecutionBuilder observation(String epoch, long lastSeq, String latestJson) {
            this.observationEpoch = epoch;
            this.lastObservationSeq = lastSeq;
            this.latestObservation = latestJson;
            return this;
        }

        /** 仅设置记录/观察流 epoch，lastObservationSeq/latestObservation 保持 NULL。 */
        public ExecutionBuilder observationEpoch(String epoch) {
            this.observationEpoch = epoch;
            return this;
        }

        public ExecutionBuilder acceptedCount(long value) {
            this.acceptedCount = value;
            return this;
        }

        public ExecutionBuilder latestVerification(String json) {
            this.latestVerification = json;
            return this;
        }

        public ExecutionBuilder lastVerifiedAt(Instant value) {
            this.lastVerifiedAt = value;
            return this;
        }

        public ExecutionBuilder stoppedAt(Instant value) {
            this.stoppedAt = value;
            return this;
        }

        public ExecutionBuilder closedAt(Instant value) {
            this.closedAt = value;
            return this;
        }

        public ExecutionBuilder createdAt(Instant value) {
            this.createdAt = value;
            return this;
        }

        public UUID insert() {
            UUID id = UUID.randomUUID();
            jdbc.update("INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                            + " controller_type, controller_account_id, controller_installation_id,"
                            + " controller_gimbal_id, assessment_id_at_start, plan_snapshot, status,"
                            + " verification_revision, last_verified_at, latest_verification,"
                            + " observation_epoch, last_observation_seq, latest_observation,"
                            + " accepted_count, stopped_at, closed_at, created_at, source_request_id)"
                            + " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?, ?,"
                            + " CAST(? AS jsonb), ?, ?, CAST(? AS jsonb), ?, ?, ?,"
                            + " COALESCE(CAST(? AS timestamptz), now()), ?)",
                    id, planId, memberId, microcrystalId, controllerType, controllerAccountId,
                    controllerInstallationId, controllerGimbalId, assessmentIdAtStart, planSnapshot,
                    status, verificationRevision,
                    lastVerifiedAt == null ? null : java.sql.Timestamp.from(lastVerifiedAt),
                    latestVerification, observationEpoch, lastObservationSeq, latestObservation,
                    acceptedCount,
                    stoppedAt == null ? null : java.sql.Timestamp.from(stoppedAt),
                    closedAt == null ? null : java.sql.Timestamp.from(closedAt),
                    createdAt == null ? null : java.sql.Timestamp.from(createdAt),
                    seedIdempotencyRequest());
            return id;
        }
    }

    // ---------- T08 ----------

    public UUID seedRecord(UUID executionId, UUID planId, UUID memberId, UUID microcrystalId,
                           String clientRecordId, String sourceEpoch, long sourceSeq, long countDelta) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id,"
                        + " microcrystal_id, count_delta, source_epoch, source_seq, payload_hash, payload)"
                        + " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'hash', CAST(? AS jsonb))",
                id, executionId, clientRecordId, planId, memberId, microcrystalId, countDelta,
                sourceEpoch, sourceSeq, "{\"schema_version\":1}");
        return id;
    }

    // ---------- 云台登录 ----------

    /** 以 gimbals 行登录云台，返回 sessionToken。 */
    public String loginGimbal(MockMvc mockMvc, UUID gimbalId) throws Exception {
        String ref = jdbc.queryForObject("SELECT auth_subject_ref FROM gimbals WHERE id=?",
                String.class, gimbalId);
        long version = jdbc.queryForObject("SELECT credential_version FROM gimbals WHERE id=?",
                Long.class, gimbalId);
        MvcResult r = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + ref + "\",\"credentialVersion\":\"" + version
                                + "\",\"proof\":\"x\"}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode data = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        return data.path("sessionToken").asText();
    }

    public static String errorTree(MvcResult result) throws Exception {
        return JSON.readTree(result.getResponse().getContentAsString()).path("error").toString();
    }
}

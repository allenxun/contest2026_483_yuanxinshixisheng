package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockMultipartHttpServletRequestBuilder;

import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * M3-A01…A06 集成测试公共支撑：真实 PG 种子（gimbals/成员/授权/报告/
 * 未收尾执行）+ multipart 构造。worker 独占列（member_id/report_*、
 * needs_retake/failed 状态）由 SQL 直接种入。
 */
abstract class AssessmentTestSupport extends AbstractWebIT {

    @Autowired
    protected JdbcTemplate jdbc;

    protected record GimbalFixture(UUID gimbalId, String token) {
    }

    protected record ReportSeed(UUID assessmentId, UUID reportId) {
    }

    protected UUID seedMember() {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO members (id) VALUES (?)", id);
        return id;
    }

    protected GimbalFixture createGimbal() throws Exception {
        String serial = "SN-D-" + UUID.randomUUID().toString().substring(0, 8);
        String authRef = "authref-" + serial;
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                + " VALUES (?, ?, ?, 3)", id, serial, authRef);
        MvcResult r = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + authRef + "\","
                                + "\"credentialVersion\":\"3\",\"proof\":\"p\"}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        String token = JSON.readTree(r.getResponse().getContentAsString())
                .path("data").path("sessionToken").asText();
        return new GimbalFixture(id, token);
    }

    protected static String a01Metadata() {
        return "{\"photoVersion\":\"1\",\"captureSessionId\":\"cs-1\","
                + "\"consentEvidenceRef\":\"ce-1\"}";
    }

    protected static byte[] png(int marker) {
        return new byte[]{(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A,
                (byte) marker, (byte) (marker >> 8), 'D', 'A', 'T', 'A'};
    }

    protected static MockMultipartFile jsonPart(String name, String json) {
        return new MockMultipartFile(name, "", "application/json",
                json.getBytes(StandardCharsets.UTF_8));
    }

    protected static MockMultipartFile imagePart(String name, byte[] bytes) {
        return new MockMultipartFile(name, name + ".png", "image/png", bytes);
    }

    protected MvcResult postA01(String token, String key, String metadataJson,
                                byte[] front, byte[] left, byte[] right) throws Exception {
        return mockMvc.perform(multipart("/api/v1/skin-assessment-tasks")
                        .file(jsonPart("metadata", metadataJson))
                        .file(imagePart("front", front))
                        .file(imagePart("left", left))
                        .file(imagePart("right", right))
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key))
                .andReturn();
    }

    protected MvcResult postA01(String token, String key) throws Exception {
        return postA01(token, key, a01Metadata(), png(1), png(2), png(3));
    }

    protected UUID acceptA01(GimbalFixture gimbal) throws Exception {
        return acceptA01(gimbal, "d-a01-" + UUID.randomUUID());
    }

    protected UUID acceptA01(GimbalFixture gimbal, String key) throws Exception {
        MvcResult r = postA01(gimbal.token(), key);
        assertEquals(202, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        return UUID.fromString(JSON.readTree(r.getResponse().getContentAsString())
                .path("data").path("taskId").asText());
    }

    protected MvcResult putA02(String token, String key, UUID taskId, long pathVersion,
                               String metadataJson, Map<String, byte[]> parts) throws Exception {
        MockMultipartHttpServletRequestBuilder builder =
                multipart(org.springframework.http.HttpMethod.PUT,
                        "/api/v1/skin-assessment-tasks/" + taskId
                        + "/photo-versions/" + pathVersion)
                        .file(jsonPart("metadata", metadataJson));
        for (Map.Entry<String, byte[]> e : parts.entrySet()) {
            builder = builder.file(imagePart(e.getKey(), e.getValue()));
        }
        return mockMvc.perform(builder
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key))
                .andReturn();
    }

    protected static JsonNode data(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("data");
    }

    protected static JsonNode error(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error");
    }

    protected UUID insertIdempotencyRow(String operation) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO idempotency_requests (id, principal_type, principal_id,"
                        + " operation, idempotency_key, payload_hash, status)"
                        + " VALUES (?, 'test', 'seed', ?, ?, 'manual', 'succeeded')",
                id, operation, UUID.randomUUID().toString());
        return id;
    }

    protected void seedGrant(String accountId, UUID memberId, String status) {
        UUID t13 = insertIdempotencyRow("test.grant");
        jdbc.update("INSERT INTO member_access_grants (id, account_id, member_id, status,"
                        + " revoked_at, source_request_id) VALUES (?, ?, ?, ?,"
                        + (status.equals("revoked") ? " now()" : " NULL") + ", ?)",
                UUID.randomUUID(), UUID.fromString(accountId), memberId, status, t13);
    }

    protected UUID seedCarePlan(UUID assessmentId, UUID memberId, String generationStatus) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO care_plans (id, assessment_id, member_id, generation_status)"
                + " VALUES (?, ?, ?, ?)", id, assessmentId, memberId, generationStatus);
        return id;
    }

    /**
     * 报告发布后的 T05 行（worker 独占列由 SQL 种入）。
     *
     * @return assessmentId + reportId
     */
    protected ReportSeed seedReportReady(UUID gimbalId, UUID memberId, Instant readyAt,
                                         String reportPayloadJson) {
        UUID t13 = insertIdempotencyRow("test.assessment");
        UUID assessmentId = UUID.randomUUID();
        UUID reportId = UUID.randomUUID();
        jdbc.update("INSERT INTO skin_assessments (id, gimbal_id, member_id, status,"
                        + " current_photo_version, processing_revision, photo_versions,"
                        + " identity_result, report_id, report_payload, report_photo_version,"
                        + " report_ready_at, source_request_id)"
                        + " VALUES (?, ?, ?, 'report_ready', 1, 1, '{}'::jsonb, '{}'::jsonb,"
                        + " ?, ?::jsonb, 1, ?, ?)",
                assessmentId, gimbalId, memberId, reportId, reportPayloadJson,
                Timestamp.from(readyAt), t13);
        return new ReportSeed(assessmentId, reportId);
    }

    protected String defaultReportPayload() {
        return "{\"schema_version\":1,\"conclusion\":\"looks good\","
                + "\"metrics\":[{\"name\":\"hydration\",\"value\":\"42\",\"unit\":\"%\"}],"
                + "\"description\":\"verified description\","
                + "\"images\":[{\"media_id\":\"" + UUID.randomUUID() + "\",\"caption\":\"cap\"}],"
                + "\"model_info\":{\"provider\":\"internal\"}}";
    }

    /** 种入一个未收尾云台执行（T07）；status 通常 running 或 stopped。 */
    protected UUID seedOpenExecution(UUID gimbalId, String status) {
        UUID memberId = seedMember();
        UUID microcrystalId = UUID.randomUUID();
        jdbc.update("INSERT INTO microcrystals (id, serial_no) VALUES (?, ?)",
                microcrystalId, "MC-" + microcrystalId);
        UUID assessmentId = UUID.randomUUID();
        jdbc.update("INSERT INTO skin_assessments (id, gimbal_id, source_request_id)"
                        + " VALUES (?, ?, ?)",
                assessmentId, gimbalId, insertIdempotencyRow("test.assessment"));
        UUID planId = UUID.randomUUID();
        jdbc.update("INSERT INTO care_plans (id, assessment_id, member_id)"
                + " VALUES (?, ?, ?)", planId, assessmentId, memberId);
        UUID executionId = UUID.randomUUID();
        jdbc.update("INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                        + " controller_type, controller_gimbal_id, assessment_id_at_start,"
                        + " status, source_request_id)"
                        + " VALUES (?, ?, ?, ?, 'gimbal', ?, ?, ?, ?)",
                executionId, planId, memberId, microcrystalId, gimbalId, assessmentId, status,
                insertIdempotencyRow("test.execution"));
        return executionId;
    }

    protected void updateTaskStatus(UUID taskId, String status) {
        jdbc.update("UPDATE skin_assessments SET status = ? WHERE id = ?", status, taskId);
    }

    protected void updateNeedsRetake(UUID taskId, String failureCode, String failureDetailJson) {
        jdbc.update("UPDATE skin_assessments SET status='needs_retake', failure_code=?,"
                + " failure_detail=?::jsonb WHERE id=?", failureCode, failureDetailJson, taskId);
    }

    protected void setMember(UUID taskId, UUID memberId) {
        jdbc.update("UPDATE skin_assessments SET member_id = ? WHERE id = ?", memberId, taskId);
    }

    /** 把已有任务标为 report_ready（worker 独占列经 SQL 种入）。 */
    protected UUID markReportReady(UUID taskId, UUID memberId) {
        UUID reportId = UUID.randomUUID();
        jdbc.update("UPDATE skin_assessments SET status='report_ready', member_id=?, report_id=?,"
                        + " report_payload=?::jsonb, report_photo_version=1, report_ready_at=now()"
                        + " WHERE id=?",
                memberId, reportId, defaultReportPayload(), taskId);
        return reportId;
    }

    /**
     * 直接种入 Java 只读列（Worker 属主）：status/failure_code/failure_detail/
     * identity_result。failure_detail/identity_result 为 null 时写空对象占位。
     */
    protected void updateTaskFields(UUID taskId, String status, String failureCode,
                                    String failureDetailJson, String identityResultJson) {
        jdbc.update("UPDATE skin_assessments SET status=?, failure_code=?, failure_detail=?::jsonb,"
                        + " identity_result=?::jsonb WHERE id=?",
                status, failureCode,
                failureDetailJson == null ? "{}" : failureDetailJson,
                identityResultJson == null ? "{}" : identityResultJson, taskId);
    }

    /** 该云台该 Idempotency-Key 逻辑请求的 T13 行 id。 */
    protected UUID t13IdForGimbalKey(UUID gimbalId, String key) {
        return jdbc.queryForObject(
                "SELECT id FROM idempotency_requests WHERE principal_type='gimbal'"
                        + " AND principal_id=? AND idempotency_key=?",
                UUID.class, gimbalId.toString(), key);
    }

    /** 该云台该键 T13 请求名下未接纳媒体触发的 media.cleanup 任务数。 */
    protected int cleanupJobCountForGimbalKey(UUID gimbalId, String key) {
        return jdbc.queryForObject(
                "SELECT count(*) FROM async_jobs WHERE job_type='media.cleanup'"
                        + " AND owner_id IN (SELECT id FROM media_objects WHERE request_id ="
                        + " (SELECT id FROM idempotency_requests WHERE principal_type='gimbal'"
                        + " AND principal_id=? AND idempotency_key=?))",
                Integer.class, gimbalId.toString(), key);
    }
}

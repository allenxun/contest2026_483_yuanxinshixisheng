package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/** F3 方案 JSONB 字段级白名单投影（A01/A02/A03/A09）：未知/敏感键绝不外发。 */
class CarePlanProjectionIT extends AbstractWebIT {

    private static final String CAPABILITIES = "{\"schema_version\":1,\"revision\":\"1\"}";

    private static final String SECRET_PAYLOAD = "{\"schema_version\":1,\"title\":\"t\","
            + "\"steps\":[{\"order\":1}],\"regions\":[\"face\"],\"parameters\":{\"dose\":\"1\"},"
            + "\"provider_raw_response\":\"SECRET\",\"prompt\":\"P\",\"vendor_debug\":{\"x\":1}}";

    private static final String SECRET_SUMMARY = "{\"schema_version\":1,\"title\":\"摘要\","
            + "\"description\":\"d\",\"provider_raw_response\":\"SECRET\",\"prompt\":\"P\"}";

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    @Test
    @DisplayName("F3 A02 plan 仅白名单字段；A01 summary 过滤；全非白名单 payload → plan=null 仍 200")
    void a01AndA02Filtered() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-f3-query");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("f3-q-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedPlan(fx.seedAssessment(gimbalId, memberId), memberId, "ready",
                SECRET_SUMMARY, SECRET_PAYLOAD, 5L, 0, 0, null);

        MvcResult full = mockMvc.perform(get("/api/v1/care-plans/" + planId + "?view=full")
                        .header("Authorization", "Bearer " + login.accessToken()))
                .andReturn();
        assertEquals(200, full.getResponse().getStatus(), full.getResponse().getContentAsString());
        String fullBody = full.getResponse().getContentAsString();
        JsonNode plan = JSON.readTree(fullBody).path("data").path("plan");
        assertEquals("t", plan.path("title").asText());
        assertEquals(1, plan.path("steps").size());
        assertEquals(1, plan.path("regions").size());
        assertEquals("1", plan.path("parameters").path("dose").asText());
        assertTrue(plan.path("schema_version").isMissingNode());
        assertFalse(fullBody.contains("SECRET"));
        assertFalse(fullBody.contains("provider_raw_response"));
        assertFalse(fullBody.contains("vendor_debug"));
        assertFalse(fullBody.contains("\"prompt\""));

        MvcResult list = mockMvc.perform(get("/api/v1/members/" + memberId + "/care-plans")
                        .header("Authorization", "Bearer " + login.accessToken()))
                .andReturn();
        assertEquals(200, list.getResponse().getStatus(), list.getResponse().getContentAsString());
        String listBody = list.getResponse().getContentAsString();
        JsonNode summary = JSON.readTree(listBody).path("data").path("items").get(0)
                .path("planSummary");
        assertEquals("摘要", summary.path("title").asText());
        assertEquals("d", summary.path("description").asText());
        assertTrue(summary.path("schema_version").isMissingNode());
        assertFalse(listBody.contains("SECRET"));

        // 全非白名单键 → 过滤后空 → plan=null 仍 200
        UUID emptyPlan = fx.seedPlan(fx.seedAssessment(gimbalId, memberId), memberId, "ready",
                "{}", "{\"schema_version\":1,\"provider_raw_response\":\"SECRET\"}",
                5L, 0, 0, null);
        MvcResult empty = mockMvc.perform(get("/api/v1/care-plans/" + emptyPlan + "?view=full")
                        .header("Authorization", "Bearer " + login.accessToken()))
                .andReturn();
        assertEquals(200, empty.getResponse().getStatus(), empty.getResponse().getContentAsString());
        assertTrue(JSON.readTree(empty.getResponse().getContentAsString()).path("data")
                .path("plan").isNull());
    }

    @Test
    @DisplayName("F3 A03 planExecution 仅 execution 白名单，快照 execution_params/summary 写入即过滤")
    void a03ExecutionProjectionAndSnapshotFiltered() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-f3-a03");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("f3-a03-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedPlan(fx.seedAssessment(gimbalId, memberId), memberId, "ready",
                SECRET_SUMMARY, SECRET_PAYLOAD, 5L, 0, 0, null);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);

        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(micro, "p", planId, null, null,
                        CareAdmissionTestSupport.capture("c", "2026-09-10T04:00:00Z", "cc", "admission"),
                        "consent"),
                CareAdmissionTestSupport.PNG);
        assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        String body = r.getResponse().getContentAsString();
        JsonNode execution = JSON.readTree(body).path("data").path("planExecution");
        assertEquals(1, execution.path("steps").size());
        assertTrue(execution.path("title").isMissingNode());
        assertFalse(body.contains("SECRET"));

        UUID executionId = UUID.fromString(JSON.readTree(body).path("data")
                .path("executionId").asText());
        String snapshot = jdbc.queryForObject(
                "SELECT plan_snapshot::text FROM care_executions WHERE id = ?", String.class,
                executionId);
        assertTrue(snapshot.contains("\"steps\""));
        assertFalse(snapshot.contains("SECRET"));
        assertFalse(snapshot.contains("vendor_debug"));
        assertFalse(snapshot.contains("provider_raw_response"));
        assertFalse(snapshot.contains("\"prompt\""));
        // 快照 summary 亦已过滤（title/description 保留，敏感键丢弃）
        assertTrue(snapshot.contains("摘要"));
    }

    @Test
    @DisplayName("F3 A09 快照摘要过滤：provider 键不外发")
    void a09SnapshotSummaryFiltered() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-f3-a09");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("f3-a09-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        fx.execution(planId, memberId, fx.seedMicrocrystal(), fx.seedAssessment(gimbalId, memberId))
                .controllerApp(accountId, "inst-f3-a09")
                .planSnapshot("{\"schema_version\":1,\"summary\":{\"title\":\"快照A\","
                        + "\"provider_raw_response\":\"SECRET\"}}")
                .insert();

        MvcResult r = mockMvc.perform(get("/api/v1/members/" + memberId + "/care-executions")
                        .header("Authorization", "Bearer " + login.accessToken()))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        String body = r.getResponse().getContentAsString();
        JsonNode summary = JSON.readTree(body).path("data").path("items").get(0)
                .path("planSnapshotSummary");
        assertEquals("快照A", summary.path("title").asText());
        assertFalse(body.contains("SECRET"));
    }
}

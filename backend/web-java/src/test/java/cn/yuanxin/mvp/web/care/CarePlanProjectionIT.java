package cn.yuanxin.mvp.web.care;

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

/**
 * F3/BLOCKER-1 方案 JSONB <b>递归</b>白名单投影（A01/A02/A03/A09）：
 * 顶层与嵌套（step/parameter/regions）未知或敏感键绝不外发，也绝不冻结进快照。
 */
class CarePlanProjectionIT extends AbstractCareIT {

    private static final String CAPABILITIES = CareTestFixtures.DEFAULT_CAPABILITIES;

    /** 顶层 + steps/parameters/regions 嵌套均埋入未知/敏感键（step 参数保持可覆盖形状）。 */
    private static final String SECRET_PAYLOAD = "{\"schema_version\":1,"
            + "\"title\":\"t\",\"description\":\"desc\","
            + "\"steps\":["
            + "  {\"region\":\"face\",\"parameters\":{\"intensity\":{\"value\":\"3\","
            + "     \"unit\":\"level\",\"internal_key\":\"SECRET_PARAM\"}},"
            + "   \"provider_raw_response\":\"SECRET_STEP_RAW\",\"prompt\":\"P_STEP\","
            + "   \"vendor_debug\":{\"x\":1}},"
            + "  {\"region\":\"face\",\"parameters\":{\"intensity\":\"4\"},\"note\":\"N\"}"
            + "],"
            + "\"regions\":[\"face\",42,\"neck\",{\"k\":1}],"
            + "\"parameters\":{\"intensity\":{\"value\":\"2\",\"unit\":\"level\","
            + "   \"internal_key\":\"SECRET_PARAMDEF\"},\"dose\":\"1\"},"
            + "\"provider_raw_response\":\"SECRET\",\"prompt\":\"P\",\"vendor_debug\":{\"x\":1}}";

    private static final String SECRET_SUMMARY = "{\"schema_version\":1,\"title\":\"摘要\","
            + "\"description\":\"d\",\"provider_raw_response\":\"SECRET\",\"prompt\":\"P\","
            + "\"vendor_debug\":{\"x\":1}}";

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private static void assertNoSensitiveSubstrings(String body) {
        assertFalse(body.contains("SECRET"), body);
        assertFalse(body.contains("P_STEP"), body);
        assertFalse(body.contains("provider_raw_response"), body);
        assertFalse(body.contains("vendor_debug"), body);
        assertFalse(body.contains("internal_key"), body);
        assertFalse(body.contains("\"prompt\""), body);
    }

    @Test
    @DisplayName("B1 A02 顶层+嵌套白名单：steps/parameters/regions 内部敏感键逐字节不外发")
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
        assertEquals("desc", plan.path("description").asText());
        assertEquals(2, plan.path("steps").size());
        // step 内未知键丢弃，合法 region/parameters 保留
        assertEquals("face", plan.path("steps").get(0).path("region").asText());
        assertEquals("3",
                plan.path("steps").get(0).path("parameters").path("intensity").path("value").asText());
        assertEquals("level",
                plan.path("steps").get(0).path("parameters").path("intensity").path("unit").asText());
        assertEquals("4", plan.path("steps").get(1).path("parameters").path("intensity").asText());
        // regions 非 string 元素丢弃
        assertEquals(2, plan.path("regions").size());
        assertEquals("face", plan.path("regions").get(0).asText());
        assertEquals("neck", plan.path("regions").get(1).asText());
        // 顶层 parameters 递归保留 value/unit 与合法标量，未知键丢弃
        assertEquals("2", plan.path("parameters").path("intensity").path("value").asText());
        assertEquals("level", plan.path("parameters").path("intensity").path("unit").asText());
        assertEquals("1", plan.path("parameters").path("dose").asText());
        assertTrue(plan.path("schema_version").isMissingNode());
        assertNoSensitiveSubstrings(fullBody);

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
        assertNoSensitiveSubstrings(listBody);

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
    @DisplayName("B1 A03 planExecution 与 T07 快照 execution_params 递归过滤，嵌套敏感键不冻结")
    void a03ExecutionProjectionAndSnapshotFiltered() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-f3-a03");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("f3-a03-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedPlan(fx.seedAssessment(gimbalId, memberId), memberId, "ready",
                SECRET_SUMMARY, SECRET_PAYLOAD, 5L, 0, 0, null);
        fx.setPlanInputSnapshot(planId, CareTestFixtures.DEFAULT_INPUT_SNAPSHOT);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);
        bindFaceMember(memberId);

        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(micro, "p", planId, null, null,
                        CareAdmissionTestSupport.capture("c", "2026-09-10T04:00:00Z", "cc", "admission"),
                        "consent"),
                CareAdmissionTestSupport.PNG);
        assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        String body = r.getResponse().getContentAsString();
        JsonNode execution = JSON.readTree(body).path("data").path("planExecution");
        assertEquals(2, execution.path("steps").size());
        assertTrue(execution.path("title").isMissingNode());
        assertNoSensitiveSubstrings(body);

        UUID executionId = UUID.fromString(JSON.readTree(body).path("data")
                .path("executionId").asText());
        String snapshot = jdbc.queryForObject(
                "SELECT plan_snapshot::text FROM care_executions WHERE id = ?", String.class,
                executionId);
        assertTrue(snapshot.contains("\"steps\""));
        assertTrue(snapshot.contains("\"regions\""));
        assertTrue(snapshot.contains("\"parameters\""));
        assertFalse(snapshot.contains("SECRET"));
        assertFalse(snapshot.contains("P_STEP"));
        assertFalse(snapshot.contains("vendor_debug"));
        assertFalse(snapshot.contains("provider_raw_response"));
        assertFalse(snapshot.contains("internal_key"));
        assertFalse(snapshot.contains("\"prompt\""));
        // 快照 summary 亦已过滤（title/description 保留，敏感键丢弃）
        assertTrue(snapshot.contains("摘要"));
    }

    @Test
    @DisplayName("B1 A09 快照摘要递归过滤：嵌套 provider 键不外发")
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
                        + "\"provider_raw_response\":\"SECRET\",\"vendor_debug\":{\"x\":1}}}")
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
        assertFalse(body.contains("vendor_debug"));
        assertFalse(body.contains("provider_raw_response"));
    }
}

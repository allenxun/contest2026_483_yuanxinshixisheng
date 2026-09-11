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
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/** M4-A01 列表 + M4-A02 完整版查询集成测试（真实 PG）。 */
class CarePlanQueryIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private MvcResult getPlans(String token, UUID memberId, String query) throws Exception {
        return mockMvc.perform(get("/api/v1/members/" + memberId + "/care-plans" + query)
                .header("Authorization", "Bearer " + token)).andReturn();
    }

    private MvcResult getPlan(String token, UUID planId, String query) throws Exception {
        return mockMvc.perform(get("/api/v1/care-plans/" + planId + query)
                .header("Authorization", "Bearer " + token)).andReturn();
    }

    // ---------------- M4-A01 ----------------

    @Test
    @DisplayName("A01 授权账号 200：waiting_inputs+ready 混合，ready 带 Progress，bigint 为字符串，no-store")
    void a01ListMixed() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a01-mixed");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("a01-gimbal-" + UUID.randomUUID(), 1);

        UUID waitingAssessment = fx.seedAssessment(gimbalId, memberId);
        UUID waitingPlan = fx.seedWaitingPlan(waitingAssessment, memberId,
                "{\"schema_version\":1,\"title\":\"等待摘要\"}");
        UUID readyAssessment = fx.seedAssessment(gimbalId, memberId);
        UUID readyPlan = fx.seedReadyPlan(readyAssessment, memberId, 10, 3, 2, null);

        MvcResult r = getPlans(login.accessToken(), memberId, "");
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        JsonNode data = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals(2, data.path("items").size());
        assertTrue(data.path("nextCursor").isNull());

        JsonNode waiting = itemById(data.path("items"), waitingPlan);
        assertEquals("waiting_inputs", waiting.path("generationStatus").asText());
        assertEquals("等待摘要", waiting.path("planSummary").path("title").asText());
        assertTrue(waiting.path("progress").isNull());

        JsonNode ready = itemById(data.path("items"), readyPlan);
        assertEquals("ready", ready.path("generationStatus").asText());
        JsonNode progress = ready.path("progress");
        assertTrue(progress.path("targetCount").isTextual());
        assertEquals("10", progress.path("targetCount").asText());
        assertEquals("3", progress.path("completedCount").asText());
        assertEquals("7", progress.path("remainingCount").asText());
        assertFalse(progress.path("isCompleted").asBoolean(true));
        assertEquals("2", progress.path("progressRevision").asText());
        assertTrue(progress.path("completedAt").isNull());
    }

    @Test
    @DisplayName("A01 未授权/已撤销/随机 memberId 三态统一 404，error 子树逐字段全等")
    void a01ThreeStateNotFoundEqual() throws Exception {
        LoginResult authorized = loginAppWithInstallation(newPhone(), "inst-a01-rev");
        UUID accountId = UUID.fromString(authorized.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");

        LoginResult unauthorized = loginAppWithInstallation(newPhone(), "inst-a01-unauth");
        String unauthorizedTree = CareTestFixtures.errorTree(
                getPlans(unauthorized.accessToken(), memberId, ""));
        assertEquals(404, getPlans(unauthorized.accessToken(), memberId, "").getResponse().getStatus());

        fx.revokeGrant(accountId, memberId);
        MvcResult revoked = getPlans(authorized.accessToken(), memberId, "");
        assertEquals(404, revoked.getResponse().getStatus());
        String revokedTree = CareTestFixtures.errorTree(revoked);

        MvcResult random = getPlans(authorized.accessToken(), UUID.randomUUID(), "");
        assertEquals(404, random.getResponse().getStatus());
        String randomTree = CareTestFixtures.errorTree(random);

        assertEquals(unauthorizedTree, revokedTree);
        assertEquals(unauthorizedTree, randomTree);
        assertTrue(JSON.readTree(unauthorizedTree).path("code").asText()
                .equals("RESOURCE_NOT_VISIBLE"));
    }

    @Test
    @DisplayName("A01 云台 token → 403 CALLER_NOT_ALLOWED（先于资源读取）")
    void a01GimbalForbidden() throws Exception {
        UUID gimbalId = fx.seedGimbal("a01-gimbal-login-" + UUID.randomUUID(), 1);
        String gimbalToken = fx.loginGimbal(mockMvc, gimbalId);
        MvcResult r = getPlans(gimbalToken, UUID.randomUUID(), "");
        assertEquals(403, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("CALLER_NOT_ALLOWED",
                JSON.readTree(r.getResponse().getContentAsString()).path("error").path("code").asText());
    }

    @Test
    @DisplayName("A01 授权但无方案 → 200 items=[] nextCursor=null")
    void a01EmptyList() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a01-empty");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        MvcResult r = getPlans(login.accessToken(), memberId, "");
        assertEquals(200, r.getResponse().getStatus());
        JsonNode data = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals(0, data.path("items").size());
        assertTrue(data.path("nextCursor").isNull());
    }

    @Test
    @DisplayName("A01 reportId 过滤：命中只返回引用方案；他人/不存在报告 → 空页不 404")
    void a01ReportIdFilter() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a01-report");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        UUID gimbalId = fx.seedGimbal("a01-report-gimbal-" + UUID.randomUUID(), 1);

        UUID reportId = UUID.randomUUID();
        UUID reportAssessment = fx.seedReportAssessment(gimbalId, memberId, reportId);
        UUID reportPlan = fx.seedReadyPlan(reportAssessment, memberId, 5, 0, 0, null);
        UUID plainAssessment = fx.seedAssessment(gimbalId, memberId);
        fx.seedWaitingPlan(plainAssessment, memberId, "{}");

        MvcResult hit = getPlans(login.accessToken(), memberId, "?reportId=" + reportId);
        assertEquals(200, hit.getResponse().getStatus());
        JsonNode data = JSON.readTree(hit.getResponse().getContentAsString()).path("data");
        assertEquals(1, data.path("items").size());
        assertEquals(reportPlan.toString(), data.path("items").get(0).path("planId").asText());

        // 他人报告（另一成员）
        UUID otherMember = fx.seedMember();
        UUID otherReport = UUID.randomUUID();
        fx.seedReportAssessment(fx.seedGimbal("a01-other-g-" + UUID.randomUUID(), 1), otherMember, otherReport);
        MvcResult foreign = getPlans(login.accessToken(), memberId, "?reportId=" + otherReport);
        assertEquals(200, foreign.getResponse().getStatus());
        JsonNode foreignData = JSON.readTree(foreign.getResponse().getContentAsString()).path("data");
        assertEquals(0, foreignData.path("items").size());
        // 不存在的报告同样空页
        MvcResult missing = getPlans(login.accessToken(), memberId, "?reportId=" + UUID.randomUUID());
        assertEquals(200, missing.getResponse().getStatus());
        assertEquals(0, JSON.readTree(missing.getResponse().getContentAsString())
                .path("data").path("items").size());
    }

    @Test
    @DisplayName("A01 limit=2 键集翻页续页正确；非法 cursor/limit 400")
    void a01PaginationAndLimit() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a01-page");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        UUID gimbalId = fx.seedGimbal("a01-page-gimbal-" + UUID.randomUUID(), 1);
        Instant base = Instant.now().minusSeconds(300);
        UUID[] plans = new UUID[3];
        for (int i = 0; i < 3; i++) {
            UUID assessment = fx.seedAssessment(gimbalId, memberId);
            plans[i] = fx.seedWaitingPlan(assessment, memberId, "{}");
            fx.setPlanCreatedAt(plans[i], base.plusSeconds(i));
        }

        MvcResult first = getPlans(login.accessToken(), memberId, "?limit=2");
        assertEquals(200, first.getResponse().getStatus());
        JsonNode d1 = JSON.readTree(first.getResponse().getContentAsString()).path("data");
        assertEquals(2, d1.path("items").size());
        // created_at DESC：最新两个（plans[2], plans[1]）
        assertEquals(plans[2].toString(), d1.path("items").get(0).path("planId").asText());
        assertEquals(plans[1].toString(), d1.path("items").get(1).path("planId").asText());
        String cursor = d1.path("nextCursor").asText();
        assertFalse(cursor.isBlank());

        MvcResult second = getPlans(login.accessToken(), memberId, "?limit=2&cursor=" + cursor);
        JsonNode d2 = JSON.readTree(second.getResponse().getContentAsString()).path("data");
        assertEquals(1, d2.path("items").size());
        assertEquals(plans[0].toString(), d2.path("items").get(0).path("planId").asText());
        assertTrue(d2.path("nextCursor").isNull());

        assertEquals(400, getPlans(login.accessToken(), memberId, "?cursor=%%%not-base64%%%")
                .getResponse().getStatus());
        assertEquals(400, getPlans(login.accessToken(), memberId, "?limit=0").getResponse().getStatus());
        assertEquals(400, getPlans(login.accessToken(), memberId, "?limit=101").getResponse().getStatus());
    }

    // ---------------- M4-A02 ----------------

    @Test
    @DisplayName("A02 ready → plan 原对象透传 + Progress")
    void a02ReadyFullView() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a02-ready");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        UUID gimbalId = fx.seedGimbal("a02-ready-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 4, 4, 3,
                Instant.parse("2026-09-10T04:00:00Z"));

        MvcResult r = getPlan(login.accessToken(), planId, "?view=full");
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        JsonNode data = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals("ready", data.path("generationStatus").asText());
        assertEquals("完整方案", data.path("plan").path("title").asText());
        assertEquals("4", data.path("progress").path("targetCount").asText());
        assertEquals("4", data.path("progress").path("completedCount").asText());
        assertEquals("0", data.path("progress").path("remainingCount").asText());
        assertTrue(data.path("progress").path("isCompleted").asBoolean());
        assertEquals("2026-09-10T04:00:00Z", data.path("progress").path("completedAt").asText());
        assertTrue(data.path("waitingReason").isNull());
    }

    @Test
    @DisplayName("A02 waiting_inputs → waitingReason；failed → generation_failed 且不泄露 failure_detail")
    void a02NotReadyReasons() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a02-reason");
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        UUID gimbalId = fx.seedGimbal("a02-reason-g-" + UUID.randomUUID(), 1);
        UUID waiting = fx.seedWaitingPlan(fx.seedAssessment(gimbalId, memberId), memberId, "{}");
        UUID failed = fx.seedFailedPlan(fx.seedAssessment(gimbalId, memberId), memberId,
                "{\"internal\":\"SECRET_INTERNAL_DIAG\"}");

        MvcResult w = getPlan(login.accessToken(), waiting, "");
        JsonNode wd = JSON.readTree(w.getResponse().getContentAsString()).path("data");
        assertEquals("waiting_inputs", wd.path("generationStatus").asText());
        assertEquals("waiting_inputs", wd.path("waitingReason").asText());
        assertTrue(wd.path("plan").isNull());
        assertTrue(wd.path("progress").isNull());

        MvcResult f = getPlan(login.accessToken(), failed, "");
        JsonNode fd = JSON.readTree(f.getResponse().getContentAsString()).path("data");
        assertEquals("failed", fd.path("generationStatus").asText());
        assertEquals("generation_failed", fd.path("waitingReason").asText());
        assertFalse(f.getResponse().getContentAsString().contains("SECRET_INTERNAL_DIAG"));
    }

    @Test
    @DisplayName("A02 云台 → 403；view=brief → 400；无授权与不存在 planId 404 全等 404")
    void a02ForbiddenBadViewAndNotFound() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-a02-err");
        UUID memberId = fx.seedMember();
        UUID gimbalId = fx.seedGimbal("a02-err-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 1, 0, 0, null);

        // 有 plan 但无授权（grant 未建）
        MvcResult noGrant = getPlan(login.accessToken(), planId, "");
        assertEquals(404, noGrant.getResponse().getStatus());
        String noGrantTree = CareTestFixtures.errorTree(noGrant);
        MvcResult missing = getPlan(login.accessToken(), UUID.randomUUID(), "");
        assertEquals(404, missing.getResponse().getStatus());
        assertEquals(noGrantTree, CareTestFixtures.errorTree(missing));

        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        MvcResult badView = getPlan(login.accessToken(), planId, "?view=brief");
        assertEquals(400, badView.getResponse().getStatus());
        assertEquals("INVALID_INPUT",
                JSON.readTree(badView.getResponse().getContentAsString()).path("error").path("code").asText());

        String gimbalToken = fx.loginGimbal(mockMvc, gimbalId);
        MvcResult cloud = getPlan(gimbalToken, planId, "");
        assertEquals(403, cloud.getResponse().getStatus());
        assertEquals("CALLER_NOT_ALLOWED",
                JSON.readTree(cloud.getResponse().getContentAsString()).path("error").path("code").asText());
    }

    private static JsonNode itemById(JsonNode items, UUID planId) {
        for (JsonNode item : items) {
            if (planId.toString().equals(item.path("planId").asText())) {
                return item;
            }
        }
        throw new AssertionError("plan not found in items: " + planId);
    }
}

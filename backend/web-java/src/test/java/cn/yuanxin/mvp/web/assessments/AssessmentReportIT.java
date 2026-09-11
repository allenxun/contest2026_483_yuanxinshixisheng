package cn.yuanxin.mvp.web.assessments;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.time.Instant;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/** M3-A04 报告列表 / M3-A05 报告投影（真实 PG）：鉴权、游标、白名单、no-store。 */
class AssessmentReportIT extends AssessmentTestSupport {

    private MvcResult list(String token, UUID memberId, Integer limit, String cursor)
            throws Exception {
        var req = get("/api/v1/members/" + memberId + "/skin-reports");
        if (limit != null) {
            req = req.param("limit", String.valueOf(limit));
        }
        if (cursor != null) {
            req = req.param("cursor", cursor);
        }
        return mockMvc.perform(req.header("Authorization", "Bearer " + token)).andReturn();
    }

    private MvcResult report(String token, UUID reportId, String view) throws Exception {
        var req = get("/api/v1/skin-reports/" + reportId);
        if (view != null) {
            req = req.param("view", view);
        }
        return mockMvc.perform(req.header("Authorization", "Bearer " + token)).andReturn();
    }

    // ----------------------------------------------------------------- A04

    @Test
    @DisplayName("A04 云台 → 403；无授权 → 404；撤销授权 → 404")
    void listAuthorization() throws Exception {
        GimbalFixture gimbal = createGimbal();
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a04-auth");
        UUID memberId = seedMember();

        MvcResult gimbalCall = list(gimbal.token(), memberId, null, null);
        assertEquals(403, gimbalCall.getResponse().getStatus(), gimbalCall.getResponse().getContentAsString());
        assertEquals("CALLER_NOT_ALLOWED", error(gimbalCall).path("code").asText());

        MvcResult noGrant = list(app.accessToken(), memberId, null, null);
        assertEquals(404, noGrant.getResponse().getStatus(), noGrant.getResponse().getContentAsString());
        assertEquals("RESOURCE_NOT_VISIBLE", error(noGrant).path("code").asText());

        seedGrant(app.accountId(), memberId, "revoked");
        MvcResult revoked = list(app.accessToken(), memberId, null, null);
        assertEquals(404, revoked.getResponse().getStatus());
    }

    @Test
    @DisplayName("A04 游标分页：limit=2 → 2 items + cursor → 第二页；reportSummary 透传；no-store")
    void listPagination() throws Exception {
        GimbalFixture gimbal = createGimbal();
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a04-page");
        UUID memberId = seedMember();
        seedGrant(app.accountId(), memberId, "active");

        Instant base = Instant.parse("2026-09-01T00:00:00Z");
        ReportSeed oldest = seedReportReady(gimbal.gimbalId(), memberId, base, defaultReportPayload());
        seedReportReady(gimbal.gimbalId(), memberId, base.plusSeconds(1), defaultReportPayload());
        seedReportReady(gimbal.gimbalId(), memberId, base.plusSeconds(2), defaultReportPayload());
        jdbc.update("UPDATE skin_assessments SET report_summary='{\"schema_version\":1,\"score\":\"oldest\"}'::jsonb"
                + " WHERE id=?", oldest.assessmentId());

        // 非 report_ready 行（queued）不得出现
        UUID queuedTask = acceptA01(gimbal);
        setMember(queuedTask, memberId);

        MvcResult page1 = list(app.accessToken(), memberId, 2, null);
        assertEquals(200, page1.getResponse().getStatus(), page1.getResponse().getContentAsString());
        assertEquals("no-store", page1.getResponse().getHeader("Cache-Control"));
        JsonNode d1 = data(page1);
        assertEquals(2, d1.path("items").size());
        assertFalse(d1.path("nextCursor").isNull());
        assertTrue(d1.path("nextCursor").asText().length() > 0);

        MvcResult page2 = list(app.accessToken(), memberId, 2, d1.path("nextCursor").asText());
        assertEquals(200, page2.getResponse().getStatus(), page2.getResponse().getContentAsString());
        JsonNode d2 = data(page2);
        assertEquals(1, d2.path("items").size());
        assertTrue(d2.path("nextCursor").isNull());
        assertEquals(oldest.reportId().toString(), d2.path("items").get(0).path("reportId").asText());
        assertEquals("oldest", d2.path("items").get(0).path("reportSummary").path("score").asText());
        assertNotNull(d2.path("items").get(0).path("reportReadyAt").asText(null));
    }

    @Test
    @DisplayName("A04 空列表 → []；非法游标 → 400")
    void listEmptyAndBadCursor() throws Exception {
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a04-empty");
        UUID memberId = seedMember();
        seedGrant(app.accountId(), memberId, "active");

        MvcResult empty = list(app.accessToken(), memberId, null, null);
        assertEquals(200, empty.getResponse().getStatus());
        assertEquals(0, data(empty).path("items").size());
        assertTrue(data(empty).path("nextCursor").isNull());

        MvcResult bad = list(app.accessToken(), memberId, null, "not-a-cursor!!");
        assertEquals(400, bad.getResponse().getStatus(), bad.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(bad).path("code").asText());
    }

    @Test
    @DisplayName("A04 limit 越界（0 / 101）→ 400 INVALID_INPUT")
    void limitOutOfRange() throws Exception {
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a04-limit");
        UUID memberId = seedMember();
        seedGrant(app.accountId(), memberId, "active");
        for (int bad : new int[]{0, 101}) {
            MvcResult r = list(app.accessToken(), memberId, bad, null);
            assertEquals(400, r.getResponse().getStatus(),
                    "limit=" + bad + ": " + r.getResponse().getContentAsString());
            assertEquals("INVALID_INPUT", error(r).path("code").asText());
        }
    }

    // ----------------------------------------------------------------- A05

    @Test
    @DisplayName("A05 APP full：白名单字段 + contentUrl；model_info/未知键/marker/caption 不泄露")
    void appFullProjection() throws Exception {
        GimbalFixture gimbal = createGimbal();
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a05-full");
        UUID memberId = seedMember();
        seedGrant(app.accountId(), memberId, "active");
        String mediaId = UUID.randomUUID().toString();
        String payload = "{\"schema_version\":1,\"conclusion\":\"ok\","
                + "\"metrics\":[{\"name\":\"hydration\",\"value\":\"42\",\"unit\":\"%\"}],"
                + "\"description\":\"verified\","
                + "\"images\":[{\"media_id\":\"" + mediaId + "\",\"caption\":\"cap\"}],"
                + "\"model_info\":{\"marker\":\"SECRET_MARKER\"},"
                + "\"internal_debug\":\"SECRET_MARKER\"}";
        ReportSeed seed = seedReportReady(gimbal.gimbalId(), memberId,
                Instant.parse("2026-09-02T00:00:00Z"), payload);

        MvcResult r = report(app.accessToken(), seed.reportId(), null);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        JsonNode d = data(r);
        assertEquals(seed.reportId().toString(), d.path("reportId").asText());
        assertEquals("full", d.path("view").asText());
        assertEquals(memberId.toString(), d.path("memberId").asText());
        assertEquals("ok", d.path("conclusion").asText());
        assertEquals("verified", d.path("description").asText());
        assertEquals(1, d.path("metrics").size());
        assertEquals("hydration", d.path("metrics").get(0).path("name").asText());
        assertEquals("42", d.path("metrics").get(0).path("value").asText());
        assertEquals(1, d.path("images").size());
        assertEquals(mediaId, d.path("images").get(0).path("mediaId").asText());
        assertEquals("/api/v1/media/" + mediaId + "/content",
                d.path("images").get(0).path("contentUrl").asText());
        assertTrue(d.path("planStatus").isNull());

        String raw = r.getResponse().getContentAsString();
        assertFalse(raw.contains("SECRET_MARKER"), raw);
        assertFalse(raw.contains("model_info"), raw);
        assertFalse(raw.contains("internal_debug"), raw);
        assertFalse(raw.contains("caption"), raw);
    }

    @Test
    @DisplayName("A05 APP brief：memberId/metrics/description 为 null，view=brief，images 保留")
    void appBriefProjection() throws Exception {
        GimbalFixture gimbal = createGimbal();
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a05-brief");
        UUID memberId = seedMember();
        seedGrant(app.accountId(), memberId, "active");
        ReportSeed seed = seedReportReady(gimbal.gimbalId(), memberId,
                Instant.parse("2026-09-02T00:00:00Z"), defaultReportPayload());

        MvcResult r = report(app.accessToken(), seed.reportId(), "brief");
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = data(r);
        assertEquals("brief", d.path("view").asText());
        assertTrue(d.path("memberId").isNull());
        assertTrue(d.path("metrics").isNull());
        assertTrue(d.path("description").isNull());
        assertEquals("looks good", d.path("conclusion").asText());
        assertEquals(1, d.path("images").size());
    }

    @Test
    @DisplayName("A05 APP 未授权 / 随机 reportId → 404；非法 view → 400")
    void appDenials() throws Exception {
        GimbalFixture gimbal = createGimbal();
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a05-deny");
        UUID memberId = seedMember();
        ReportSeed seed = seedReportReady(gimbal.gimbalId(), memberId,
                Instant.parse("2026-09-02T00:00:00Z"), defaultReportPayload());

        MvcResult noGrant = report(app.accessToken(), seed.reportId(), null);
        assertEquals(404, noGrant.getResponse().getStatus(), noGrant.getResponse().getContentAsString());

        seedGrant(app.accountId(), memberId, "active");
        MvcResult random = report(app.accessToken(), UUID.randomUUID(), null);
        assertEquals(404, random.getResponse().getStatus());

        MvcResult badView = report(app.accessToken(), seed.reportId(), "bogus");
        assertEquals(400, badView.getResponse().getStatus(), badView.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(badView).path("code").asText());
    }

    @Test
    @DisplayName("A05 损坏 report_payload（内部字段类型错误）→ 500 INTERNAL，不泄露内容")
    void malformedPayload() throws Exception {
        GimbalFixture gimbal = createGimbal();
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a05-bad");
        UUID memberId = seedMember();
        seedGrant(app.accountId(), memberId, "active");
        // jsonb CHECK 要求 object + 数字 schema_version；用内部字段类型错误触发防御分支
        String payload = "{\"schema_version\":1,\"conclusion\":\"SECRET_MARKER\","
                + "\"metrics\":\"SECRET_MARKER\"}";
        ReportSeed seed = seedReportReady(gimbal.gimbalId(), memberId,
                Instant.parse("2026-09-02T00:00:00Z"), payload);

        MvcResult r = report(app.accessToken(), seed.reportId(), null);
        assertEquals(500, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("INTERNAL", error(r).path("code").asText());
        assertFalse(r.getResponse().getContentAsString().contains("SECRET_MARKER"),
                r.getResponse().getContentAsString());
    }

    @Test
    @DisplayName("A05 云台当前任务报告 → brief；view=full → 403；被替换 → 409；他人 → 404")
    void gimbalViews() throws Exception {
        GimbalFixture gimbal = createGimbal();
        UUID memberId = seedMember();
        UUID taskId = acceptA01(gimbal);
        UUID reportId = markReportReady(taskId, memberId);

        MvcResult brief = report(gimbal.token(), reportId, null);
        assertEquals(200, brief.getResponse().getStatus(), brief.getResponse().getContentAsString());
        assertEquals("brief", data(brief).path("view").asText());

        MvcResult full = report(gimbal.token(), reportId, "full");
        assertEquals(403, full.getResponse().getStatus(), full.getResponse().getContentAsString());
        assertEquals("CALLER_NOT_ALLOWED", error(full).path("code").asText());

        // 被替换：指针移到新任务
        acceptA01(gimbal);
        MvcResult replaced = report(gimbal.token(), reportId, null);
        assertEquals(409, replaced.getResponse().getStatus(), replaced.getResponse().getContentAsString());
        assertEquals("TASK_REPLACED", error(replaced).path("code").asText());

        // 他人云台
        GimbalFixture other = createGimbal();
        UUID member2 = seedMember();
        UUID task2 = acceptA01(other);
        UUID report2 = markReportReady(task2, member2);
        MvcResult foreign = report(gimbal.token(), report2, null);
        assertEquals(404, foreign.getResponse().getStatus(), foreign.getResponse().getContentAsString());
    }

    @Test
    @DisplayName("A05 planStatus 反映关联方案生成状态")
    void planStatus() throws Exception {
        GimbalFixture gimbal = createGimbal();
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-a05-plan");
        UUID memberId = seedMember();
        seedGrant(app.accountId(), memberId, "active");
        ReportSeed seed = seedReportReady(gimbal.gimbalId(), memberId,
                Instant.parse("2026-09-02T00:00:00Z"), defaultReportPayload());
        seedCarePlan(seed.assessmentId(), memberId, "waiting_inputs");
        MvcResult r = report(app.accessToken(), seed.reportId(), null);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("waiting_inputs", data(r).path("planStatus").asText());
    }
}

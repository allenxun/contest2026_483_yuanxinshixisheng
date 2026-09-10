package cn.yuanxin.mvp.web.system;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Set;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * E 独立验收发现的泄漏回归（n2-http-repro）：GET echo-jobs 曾把 async_jobs.
 * last_error 原样（含 4058 字符 message / Bearer 标记）投影到 data.lastError。
 * 现强制有界安全投影（仅 reason 枚举 + retryable bool），raw 诊断绝不外泄。
 */
class EchoLastErrorProjectionIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    private String newJob(String token) throws Exception {
        MvcResult r = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json")
                        .content("{\"message\":\"leak-proj\",\"numbersAsStrings\":[\"7\"]}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        return JSON.readTree(r.getResponse().getContentAsString()).path("data").path("jobId").asText();
    }

    private JsonNode getData(String token, String jobId) throws Exception {
        MvcResult g = mockMvc.perform(get("/api/v1/system/echo-jobs/" + jobId)
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(200, g.getResponse().getStatus(), g.getResponse().getContentAsString());
        return JSON.readTree(g.getResponse().getContentAsString()).path("data");
    }

    private void setLastError(String jobId, String json) {
        jdbc.update("UPDATE async_jobs SET last_error = ?::jsonb WHERE id = ?::uuid", json, jobId);
    }

    private static Set<String> fieldNames(JsonNode node) {
        Set<String> names = new TreeSet<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }

    @Test
    @DisplayName("1) E 标记原样入库 → GET 不再回显 marker/Bearer；reason=internal，恰 {reason,retryable}")
    void eMarkerLeakClosed() throws Exception {
        String token = loginApp(newPhone());
        String jobId = newJob(token);
        setLastError(jobId, "{\"code\":\"E_DIAG_MARKER\","
                + "\"message\":\"Bearer E2E_DIAG_SECRET_MARKER_12345\"}");

        MvcResult g = mockMvc.perform(get("/api/v1/system/echo-jobs/" + jobId)
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(200, g.getResponse().getStatus());
        String body = g.getResponse().getContentAsString();
        assertFalse(body.contains("E2E_DIAG_SECRET_MARKER"), body);
        assertFalse(body.contains("E_DIAG_MARKER"), body);
        assertFalse(body.contains("Bearer"), body);

        JsonNode le = JSON.readTree(body).path("data").path("lastError");
        assertEquals("internal", le.path("reason").asText());
        assertTrue(le.path("retryable").isBoolean());
        assertEquals(Set.of("reason", "retryable"), fieldNames(le));
    }

    @Test
    @DisplayName("2) 4058 字符 message + stack/sql/retry_after → 全部不回显；reason=internal，retryable=true")
    void longDiagnosticBounded() throws Exception {
        String token = loginApp(newPhone());
        String jobId = newJob(token);
        String longMsg = "L".repeat(4058);
        setLastError(jobId, "{\"code\":\"E_DIAG_LONG\",\"message\":\"" + longMsg
                + "\",\"stack\":\"STACKTRACE_MARKER_XYZ\",\"sql\":\"SELECT 1 FROM secret\","
                + "\"retry_after_seconds\":99,\"retryable\":true}");

        MvcResult g = mockMvc.perform(get("/api/v1/system/echo-jobs/" + jobId)
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(200, g.getResponse().getStatus());
        String body = g.getResponse().getContentAsString();
        assertFalse(body.contains("LLLL"), body);
        assertFalse(body.contains("STACKTRACE_MARKER_XYZ"), body);
        assertFalse(body.contains("SELECT 1 FROM secret"), body);
        assertFalse(body.contains("\"sql\""), body);
        assertFalse(body.contains("retry_after_seconds"), body);
        assertFalse(body.contains("E_DIAG_LONG"), body);

        JsonNode le = JSON.readTree(body).path("data").path("lastError");
        assertEquals("internal", le.path("reason").asText());
        assertTrue(le.path("retryable").asBoolean());
        assertEquals(Set.of("reason", "retryable"), fieldNames(le));
    }

    @Test
    @DisplayName("3) 已知 code UNSUPPORTED_CONTRACT → reason=unsupported_contract；message 不回显")
    void knownCodeMapped() throws Exception {
        String token = loginApp(newPhone());
        String jobId = newJob(token);
        setLastError(jobId, "{\"code\":\"UNSUPPORTED_CONTRACT\","
                + "\"message\":\"internal detail here\",\"retryable\":false}");

        JsonNode le = getData(token, jobId).path("lastError");
        assertEquals("unsupported_contract", le.path("reason").asText());
        assertFalse(le.path("retryable").asBoolean());
        String full = mockMvc.perform(get("/api/v1/system/echo-jobs/" + jobId)
                        .header("Authorization", "Bearer " + token))
                .andReturn().getResponse().getContentAsString();
        assertFalse(full.contains("internal detail here"), full);
    }

    @Test
    @DisplayName("4) 非对象 JSON / 解析失败 → reason=internal, retryable=false，绝不回显原始文本")
    void malformedOrNonObjectIsInternal() throws Exception {
        String token = loginApp(newPhone());
        String jobId = newJob(token);
        // jsonb 列无法存非法 JSON：用合法 jsonb 的非对象（数组）承载原始文本
        setLastError(jobId, "[\"not json at all {\\\"code\"]");

        MvcResult g = mockMvc.perform(get("/api/v1/system/echo-jobs/" + jobId)
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(200, g.getResponse().getStatus());
        String body = g.getResponse().getContentAsString();
        assertFalse(body.contains("not json at all"), body);
        JsonNode le = JSON.readTree(body).path("data").path("lastError");
        assertEquals("internal", le.path("reason").asText());
        assertFalse(le.path("retryable").asBoolean());
        assertEquals(Set.of("reason", "retryable"), fieldNames(le));

        // 解析失败分支（JSON 不可解析）直接单测投影：绝不返回原文
        SystemEchoController.EchoJobLastError parsed =
                SystemEchoController.projectError("not json at all {\"code");
        assertEquals("internal", parsed.reason());
        assertFalse(parsed.retryable());
    }

    @Test
    @DisplayName("5) 正常 succeeded（last_error NULL）→ lastError=null；计数仍 bigint 字符串")
    void normalSucceededUnaffected() throws Exception {
        String token = loginApp(newPhone());
        String jobId = newJob(token);

        JsonNode d = getData(token, jobId);
        assertEquals(jobId, d.path("jobId").asText());
        assertEquals("queued", d.path("status").asText());
        assertEquals("0", d.path("attemptCount").asText());
        assertTrue(d.path("attemptCount").isTextual());
        assertEquals("0", d.path("leaseRevision").asText());
        assertTrue(d.path("finishedAt").isNull());
        assertTrue(d.path("lastError").isNull());

        jdbc.update("UPDATE async_jobs SET status='succeeded', attempt_count=3,"
                + " lease_revision=2, finished_at = now() WHERE id = ?::uuid", jobId);
        JsonNode d2 = getData(token, jobId);
        assertEquals("succeeded", d2.path("status").asText());
        assertEquals("3", d2.path("attemptCount").asText());
        assertEquals("2", d2.path("leaseRevision").asText());
        assertNotNull(d2.path("finishedAt").asText());
        assertTrue(d2.path("lastError").isNull());
    }
}

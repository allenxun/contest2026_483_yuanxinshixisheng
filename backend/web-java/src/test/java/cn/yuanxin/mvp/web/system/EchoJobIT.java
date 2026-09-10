package cn.yuanxin.mvp.web.system;

import cn.yuanxin.mvp.web.jobs.Uuid5;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/** system.echo：契约固定列/owner_id/payload 形状 + GET 投影（E2E 验收桥）。 */
class EchoJobIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    @DisplayName("POST 入队 async_jobs：owner_id=uuid5(FIXED_NS,dedup_key)、schema_version=1、"
            + "bigint 字符串、queued/0/5/0 初值")
    void enqueueRowShape() throws Exception {
        String token = loginApp(newPhone());
        String clientJobId = UUID.randomUUID().toString();
        MvcResult r = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json")
                        .content("{\"message\":\"回声测试 ✓\",\"numbersAsStrings\":[\"0\","
                                + "\"9007199254740991\"],\"jobId\":\"" + clientJobId + "\"}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode data = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals("system:echo:" + clientJobId, data.path("dedupKey").asText());
        assertEquals("queued", data.path("status").asText());
        UUID jobId = UUID.fromString(data.path("jobId").asText());

        Map<String, Object> row = jdbc.queryForMap(
                "SELECT job_type, dedup_key, owner_type, owner_id::text AS owner_id,"
                        + " input_revision, status, attempt_count, max_attempts, lease_revision,"
                        + " payload::text AS payload"
                        + " FROM async_jobs WHERE id = ?", jobId);
        assertEquals("system.echo", row.get("job_type"));
        assertEquals("system:echo:" + clientJobId, row.get("dedup_key"));
        assertEquals("system", row.get("owner_type"));
        assertEquals(Uuid5.uuid5(Uuid5.FIXED_NS, "system:echo:" + clientJobId).toString(),
                row.get("owner_id"));
        assertEquals(0L, ((Number) row.get("input_revision")).longValue());
        assertEquals("queued", row.get("status"));
        assertEquals(0L, ((Number) row.get("attempt_count")).longValue());
        assertEquals(5L, ((Number) row.get("max_attempts")).longValue());
        assertEquals(0L, ((Number) row.get("lease_revision")).longValue());

        JsonNode payload = JSON.readTree((String) row.get("payload"));
        assertEquals(1, payload.path("schema_version").asInt());
        assertTrue(payload.path("schema_version").isInt());
        assertEquals("回声测试 ✓", payload.path("message").asText());
        assertEquals("0", payload.path("numbers_as_strings").get(0).asText());
        assertEquals("9007199254740991", payload.path("numbers_as_strings").get(1).asText());
        assertTrue(payload.path("numbers_as_strings").get(0).isTextual());
    }

    @Test
    @DisplayName("GET 投影随 DB 状态推进（worker 更新后可见），计数为 bigint 字符串")
    void getProjectionReflectsDb() throws Exception {
        String token = loginApp(newPhone());
        MvcResult r = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json")
                        .content("{\"message\":\"proj\",\"numbersAsStrings\":[\"123456789012345\"]}"))
                .andReturn();
        String jobId = JSON.readTree(r.getResponse().getContentAsString())
                .path("data").path("jobId").asText();

        MvcResult g = mockMvc.perform(get("/api/v1/system/echo-jobs/" + jobId)
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(200, g.getResponse().getStatus());
        JsonNode d = JSON.readTree(g.getResponse().getContentAsString()).path("data");
        assertEquals(jobId, d.path("jobId").asText());
        assertEquals("queued", d.path("status").asText());
        assertEquals("0", d.path("attemptCount").asText());
        assertTrue(d.path("attemptCount").isTextual());
        assertEquals("0", d.path("leaseRevision").asText());
        assertTrue(d.path("finishedAt").isNull());
        assertTrue(d.path("lastError").isNull());

        // 模拟 worker 领取后完成（Python 侧行为在 P 包测；此处只验投影读取）
        jdbc.update("UPDATE async_jobs SET status='succeeded', attempt_count=3,"
                + " lease_revision=2, finished_at = now() WHERE id = ?::uuid", jobId);
        MvcResult g2 = mockMvc.perform(get("/api/v1/system/echo-jobs/" + jobId)
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        JsonNode d2 = JSON.readTree(g2.getResponse().getContentAsString()).path("data");
        assertEquals("succeeded", d2.path("status").asText());
        assertEquals("3", d2.path("attemptCount").asText());
        assertEquals("2", d2.path("leaseRevision").asText());
        assertNotNull(d2.path("finishedAt").asText());
    }

    @Test
    @DisplayName("GET 未知 jobId → 404 RESOURCE_NOT_VISIBLE；非法 UUID → 400 INVALID_INPUT")
    void getErrors() throws Exception {
        String token = loginApp(newPhone());
        MvcResult nf = mockMvc.perform(get("/api/v1/system/echo-jobs/" + UUID.randomUUID())
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(404, nf.getResponse().getStatus());
        assertEquals("RESOURCE_NOT_VISIBLE",
                JSON.readTree(nf.getResponse().getContentAsString())
                        .path("error").path("code").asText());
        MvcResult bad = mockMvc.perform(get("/api/v1/system/echo-jobs/not-a-uuid")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(400, bad.getResponse().getStatus());
        assertEquals("INVALID_INPUT",
                JSON.readTree(bad.getResponse().getContentAsString())
                        .path("error").path("code").asText());
    }
}

package cn.yuanxin.mvp.web.system;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * RV-5 裁定：echo-jobs GET 仅创建者本人可读，且不存在 / 非 system.echo /
 * 非创建者 三类统一 404（不泄露存在性/归属/类型）；POST 归属写入 A 属主列，
 * T13 作用域仍含 principal（同键跨账号 = 各自新任务，不跨暴露）。
 */
class EchoOwnershipIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    private String postEcho(String token, String key, String jobId) throws Exception {
        String body = "{\"message\":\"own\",\"numbersAsStrings\":[\"1\"]"
                + (jobId == null ? "" : ",\"jobId\":\"" + jobId + "\"") + "}";
        MvcResult r = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key)
                        .contentType("application/json").content(body))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        return JSON.readTree(r.getResponse().getContentAsString()).path("data").path("jobId").asText();
    }

    private MvcResult getJob(String token, String jobId) throws Exception {
        return mockMvc.perform(get("/api/v1/system/echo-jobs/" + jobId)
                        .header("Authorization", "Bearer " + token))
                .andReturn();
    }

    private static JsonNode errorOf(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error");
    }

    @Test
    @DisplayName("(a) 创建者 GET 自己的 echo job → 200 + 正确投影")
    void creatorReadsOwn() throws Exception {
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-own-a");
        String jobId = postEcho(owner.accessToken(), "own-a-" + UUID.randomUUID(), null);

        MvcResult r = getJob(owner.accessToken(), jobId);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode d = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertEquals(jobId, d.path("jobId").asText());
        assertEquals("queued", d.path("status").asText());
        assertEquals("0", d.path("attemptCount").asText());
        assertTrue(d.path("lastError").isNull());
    }

    @Test
    @DisplayName("(b/d) 他人 GET / 随机 UUID → 统一 404，error 子树与不存在完全一致，无归属/类型泄露")
    void foreignAndMissingIdentical() throws Exception {
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-own-b1");
        String jobId = postEcho(owner.accessToken(), "own-b-" + UUID.randomUUID(), null);
        LoginResult other = loginAppWithInstallation(newPhone(), "inst-own-b2");

        MvcResult foreign = getJob(other.accessToken(), jobId);
        MvcResult missing = getJob(other.accessToken(), UUID.randomUUID().toString());
        assertEquals(404, foreign.getResponse().getStatus());
        assertEquals(404, missing.getResponse().getStatus());
        assertEquals(errorOf(foreign), errorOf(missing), "foreign vs missing error envelope must match");
        assertEquals("RESOURCE_NOT_VISIBLE", errorOf(foreign).path("code").asText());

        String body = foreign.getResponse().getContentAsString();
        assertFalse(body.contains("app_account"), body);
        assertFalse(body.contains("system.echo"), body);
        assertFalse(body.contains("owner"), body);
    }

    @Test
    @DisplayName("(c) 认证主体 GET 非 echo 的 async_jobs 行 → 同样统一 404")
    void nonEchoRowNotVisible() throws Exception {
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-own-c");
        UUID nonEchoId = UUID.randomUUID();
        // 该行 owner 与调用者一致，但 job_type 非 system.echo → 类型不匹配 → 404
        jdbc.update("INSERT INTO async_jobs (id, job_type, dedup_key, owner_type, owner_id,"
                        + " payload, status) VALUES (?, 'assessment.analyze', ?, 'app_account', ?,"
                        + " '{\"schema_version\":1}'::jsonb, 'queued')",
                nonEchoId, "non-echo-" + nonEchoId, UUID.fromString(owner.accountId()));

        MvcResult r = getJob(owner.accessToken(), nonEchoId.toString());
        MvcResult missing = getJob(owner.accessToken(), UUID.randomUUID().toString());
        assertEquals(404, r.getResponse().getStatus());
        assertEquals(errorOf(r), errorOf(missing), "non-echo vs missing error envelope must match");
    }

    @Test
    @DisplayName("(e) 创建者同 Idempotency-Key 重放 → 同 jobId + meta.replayed=true，投影不变")
    void creatorReplaySameJob() throws Exception {
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-own-e");
        String key = "own-e-" + UUID.randomUUID();
        String jobId = postEcho(owner.accessToken(), key, null);

        MvcResult r = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + owner.accessToken())
                        .header("Idempotency-Key", key)
                        .contentType("application/json")
                        .content("{\"message\":\"own\",\"numbersAsStrings\":[\"1\"]}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode body = JSON.readTree(r.getResponse().getContentAsString());
        assertEquals(jobId, body.path("data").path("jobId").asText());
        assertTrue(body.path("meta").path("replayed").asBoolean());
        assertEquals("queued", body.path("data").path("status").asText());
        assertEquals(200, getJob(owner.accessToken(), jobId).getResponse().getStatus());
    }

    @Test
    @DisplayName("(f) 第二账号同 Idempotency-Key → 不同 T13 作用域 → 各自新任务；互不可读")
    void sameKeyDifferentPrincipalSeparateJobs() throws Exception {
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-own-f1");
        LoginResult b = loginAppWithInstallation(newPhone(), "inst-own-f2");
        String key = "shared-key-" + UUID.randomUUID();

        String jobA = postEcho(a.accessToken(), key, null);
        String jobB = postEcho(b.accessToken(), key, null);

        assertNotEquals(jobA, jobB, "same Idempotency-Key across principals must not share a job");
        Integer scopeRows = jdbc.queryForObject(
                "SELECT count(*) FROM idempotency_requests WHERE operation='system.echo.create'"
                        + " AND idempotency_key = ?", Integer.class, key);
        assertEquals(2, scopeRows, "one T13 row per (principal, operation, key) scope");

        assertEquals(200, getJob(a.accessToken(), jobA).getResponse().getStatus());
        assertEquals(404, getJob(a.accessToken(), jobB).getResponse().getStatus());
        assertEquals(200, getJob(b.accessToken(), jobB).getResponse().getStatus());
        assertEquals(404, getJob(b.accessToken(), jobA).getResponse().getStatus());
    }
}

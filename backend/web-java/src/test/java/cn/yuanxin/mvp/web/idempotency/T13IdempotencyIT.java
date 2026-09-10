package cn.yuanxin.mvp.web.idempotency;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * T13 行为（DD 3.3 / digest §5）：同键同内容重放、异内容冲突、处理中租约、
 * 过期租约接管 + 旧代次完成回滚、拒绝重放。
 */
class T13IdempotencyIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    IdempotencyService service;

    @Autowired
    TransactionTemplate tx;

    @Test
    @DisplayName("HTTP：同键同内容重放 → meta.replayed=true + 同一 jobId + 单次入队")
    void replaySameKeySameContent() throws Exception {
        String token = loginApp(newPhone());
        String key = "t13-replay-" + UUID.randomUUID();
        String body = "{\"message\":\"echo-replay\",\"numbersAsStrings\":[\"1\",\"0\",\"42\"]}";
        MvcResult a = echoPost(token, key, body);
        MvcResult b = echoPost(token, key, body);
        assertEquals(200, a.getResponse().getStatus());
        assertEquals(200, b.getResponse().getStatus());
        JsonNode da = JSON.readTree(a.getResponse().getContentAsString());
        JsonNode db = JSON.readTree(b.getResponse().getContentAsString());
        assertEquals(false, da.path("meta").path("replayed").asBoolean(false));
        assertTrue(db.path("meta").path("replayed").asBoolean());
        assertEquals(da.path("data").path("jobId").asText(), db.path("data").path("jobId").asText());
        Integer jobCount = jdbc.queryForObject("SELECT count(*) FROM async_jobs WHERE dedup_key = ?",
                Integer.class, da.path("data").path("dedupKey").asText());
        assertEquals(1, jobCount);
        // 重放响应携带原逻辑结果投影（同 jobId、当前状态 queued）
        assertEquals("queued", db.path("data").path("status").asText());
    }

    @Test
    @DisplayName("HTTP：同键不同内容 → 409 IDEMPOTENCY_CONTENT_CONFLICT")
    void sameKeyDifferentContent() throws Exception {
        String token = loginApp(newPhone());
        String key = "t13-conflict-" + UUID.randomUUID();
        assertEquals(200, echoPost(token, key, "{\"message\":\"v1\",\"numbersAsStrings\":[]}")
                .getResponse().getStatus());
        MvcResult r = echoPost(token, key, "{\"message\":\"v2\",\"numbersAsStrings\":[]}");
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("IDEMPOTENCY_CONTENT_CONFLICT",
                JSON.readTree(r.getResponse().getContentAsString())
                        .path("error").path("code").asText());
    }

    @Test
    @DisplayName("HTTP：processing 且租约存活 → 409 REQUEST_IN_PROGRESS + Retry-After")
    void inProgressLeaseHolds() throws Exception {
        String token = loginApp(newPhone());
        String key = "t13-inflight-" + UUID.randomUUID();
        String body = "{\"message\":\"inflight\",\"numbersAsStrings\":[\"5\"]}";
        // 先发一次成功建立 principal 行（换键），拿到真实 principal 与 payload_hash
        MvcResult pre = echoPost(token, "t13-seed-" + key, body);
        assertEquals(200, pre.getResponse().getStatus());
        String principalId = jdbc.queryForObject(
                "SELECT principal_id FROM idempotency_requests WHERE idempotency_key = ?",
                String.class, "t13-seed-" + key);
        String principalType = jdbc.queryForObject(
                "SELECT principal_type FROM idempotency_requests WHERE idempotency_key = ?",
                String.class, "t13-seed-" + key);
        // 直接以真实行哈希复制（canonical 组装细节由 echo 端点自身验证）
        String realHash = jdbc.queryForObject(
                "SELECT payload_hash FROM idempotency_requests WHERE idempotency_key = ?",
                String.class, "t13-seed-" + key);
        jdbc.update("INSERT INTO idempotency_requests (id, principal_type, principal_id, operation,"
                        + " idempotency_key, payload_hash, status, lease_until, attempt_revision)"
                        + " VALUES (?::uuid, ?, ?, 'system.echo.create', ?, ?, 'processing',"
                        + " now() + interval '25 seconds', 1)",
                UUID.randomUUID().toString(), principalType, principalId, key, realHash);
        MvcResult r = echoPost(token, key, body);
        assertEquals(409, r.getResponse().getStatus());
        JsonNode err = JSON.readTree(r.getResponse().getContentAsString()).path("error");
        assertEquals("REQUEST_IN_PROGRESS", err.path("code").asText());
        assertTrue(err.path("retryable").asBoolean());
        assertNotNull(r.getResponse().getHeader("Retry-After"));
        assertTrue(Integer.parseInt(r.getResponse().getHeader("Retry-After")) >= 1);
    }

    @Test
    @DisplayName("服务层：租约过期接管 + 旧代次 completeSuccess 抛 StaleAttempt 且回滚")
    void expiredLeaseTakeoverAndStaleRollback() {
        String pType = "app_account";
        String pId = "acct-stale:inst-1";
        String op = "test.stale.op";
        String key = "stale-" + UUID.randomUUID();
        String hash = "hash-stale";

        BeginOutcome fresh = service.begin(pType, pId, op, key, hash);
        IdempotencyHandle first = ((BeginOutcome.NewAttempt) fresh).handle();
        assertEquals(1, first.attemptRevision());

        // 人为令租约过期
        jdbc.update("UPDATE idempotency_requests SET lease_until = now() - interval '1 second'"
                + " WHERE id = ?", first.requestId());

        BeginOutcome taken = service.begin(pType, pId, op, key, hash);
        IdempotencyHandle second = ((BeginOutcome.NewAttempt) taken).handle();
        assertEquals(2, second.attemptRevision());

        // 旧代次完成 → StaleAttempt + 事务回滚（状态仍是 processing，资源不可见）
        assertThrows(StaleAttemptException.class, () -> tx.executeWithoutResult(s ->
                service.completeSuccess(first, "async_job", UUID.randomUUID(),
                        Map.of("stale", true))));
        String status = jdbc.queryForObject("SELECT status FROM idempotency_requests WHERE id = ?",
                String.class, first.requestId());
        assertEquals("processing", status);
        Integer resourceSet = jdbc.queryForObject(
                "SELECT count(*) FROM idempotency_requests WHERE id = ? AND resource_id IS NOT NULL",
                Integer.class, first.requestId());
        assertEquals(0, resourceSet);

        // 新代次完成成功
        UUID resourceId = UUID.randomUUID();
        tx.executeWithoutResult(s -> service.completeSuccess(second, "async_job", resourceId,
                Map.of("ok", 1)));
        status = jdbc.queryForObject("SELECT status FROM idempotency_requests WHERE id = ?",
                String.class, first.requestId());
        assertEquals("succeeded", status);

        // 再次 begin：同内容 → succeeded 重放定位原资源
        BeginOutcome replay = service.begin(pType, pId, op, key, hash);
        assertTrue(replay instanceof BeginOutcome.ReplaySucceeded);
        assertEquals(resourceId, ((BeginOutcome.ReplaySucceeded) replay).resourceId());
    }

    @Test
    @DisplayName("服务层：确定性拒绝 → rejected；重试返回原拒绝")
    void rejectedReplay() {
        String pType = "gimbal";
        String pId = UUID.randomUUID().toString();
        String op = "test.reject.op";
        String key = "rej-" + UUID.randomUUID();
        String hash = "hash-rej";
        IdempotencyHandle h = ((BeginOutcome.NewAttempt) service.begin(pType, pId, op, key, hash))
                .handle();
        tx.executeWithoutResult(s -> service.completeRejected(h, ErrorCode.FACE_QUALITY_REJECTED,
                422, "face quality rejected", false, Map.of("reason", "blur")));
        BeginOutcome again = service.begin(pType, pId, op, key, hash);
        assertTrue(again instanceof BeginOutcome.ReplayRejected);
        BeginOutcome.ReplayRejected rej = (BeginOutcome.ReplayRejected) again;
        assertEquals("FACE_QUALITY_REJECTED", rej.code());
        assertEquals("blur", rej.details().path("reason").asText());
        ApiException ex = IdempotencyService.replayedRejection(rej);
        assertEquals(ErrorCode.FACE_QUALITY_REJECTED, ex.getCode());
        assertEquals(422, ex.getHttpStatus());
    }

    private MvcResult echoPost(String token, String key, String body) throws Exception {
        return mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key)
                        .contentType("application/json")
                        .content(body))
                .andReturn();
    }
}

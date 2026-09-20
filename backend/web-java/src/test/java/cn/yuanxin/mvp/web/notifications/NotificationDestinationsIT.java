package cn.yuanxin.mvp.web.notifications;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

/**
 * M5-A01（通知目标登记）真实 PG 集成测试：首建、响应最小化、相同内容不增代次、
 * 内容变化增代次、代次冲突、换号接管、越权/无效主体、幂等重放、并发首建、
 * 会话失效。
 *
 * <p>覆盖 lane-m5.md Java 必测 1～10。身份只来自 token；DB 断言在行级
 * （字段值 / 计数），不只看 HTTP 码。</p>
 */
class NotificationDestinationsIT extends AbstractWebIT {

    private static final String PROVIDER = "dev-fcm";
    private static final String PLATFORM = "android";

    @Autowired
    JdbcTemplate jdbc;

    // ---------------- helpers ----------------

    private record Dest(UUID id, UUID accountId, long revision, String provider, String platform,
                        String registration, String status, String sessionRef,
                        boolean invalidated) {
    }

    private static String body(String provider, String platform,
                               Map<String, Object> registration, String expected)
            throws Exception {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("provider", provider);
        m.put("platform", platform);
        m.put("registration", registration);
        m.put("expectedDestinationRevision", expected);
        return JSON.writeValueAsString(m);
    }

    private static Map<String, Object> registration(String token) {
        Map<String, Object> reg = new LinkedHashMap<>();
        reg.put("token", token);
        return reg;
    }

    private MvcResult putJson(String token, String installationId, String json, String key)
            throws Exception {
        var builder = put("/api/v1/me/notification-destinations/" + installationId)
                .contentType("application/json").content(json);
        if (token != null) {
            builder.header("Authorization", "Bearer " + token);
        }
        if (key != null) {
            builder.header("Idempotency-Key", key);
        }
        return mockMvc.perform(builder).andReturn();
    }

    private Dest destOf(String installationId) {
        List<Dest> rows = jdbc.query("SELECT id, account_id, destination_revision, provider,"
                        + " platform, registration::text AS registration, status, session_ref,"
                        + " invalidated_at FROM notification_destinations WHERE installation_id = ?",
                (rs, i) -> new Dest(rs.getObject("id", UUID.class),
                        rs.getObject("account_id", UUID.class), rs.getLong("destination_revision"),
                        rs.getString("provider"), rs.getString("platform"),
                        rs.getString("registration"), rs.getString("status"),
                        rs.getString("session_ref"), rs.getTimestamp("invalidated_at") != null),
                installationId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private long destCount(String installationId) {
        Long n = jdbc.queryForObject(
                "SELECT count(*) FROM notification_destinations WHERE installation_id = ?",
                Long.class, installationId);
        return n == null ? 0 : n;
    }

    private static JsonNode data(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("data");
    }

    private static JsonNode error(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error");
    }

    private UUID seedGimbal() {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                        + " VALUES (?, ?, ?, 1)",
                id, "gimbal-notif-" + id, "cred-" + id);
        return id;
    }

    private String gimbalToken(UUID gimbalId) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"cred-" + gimbalId
                                + "\",\"credentialVersion\":\"1\",\"proof\":\"dev-proof\"}"))
                .andReturn();
        assertEquals(200, result.getResponse().getStatus(),
                result.getResponse().getContentAsString());
        return data(result).path("sessionToken").asText();
    }

    // ---------------- 1. first registration ----------------

    @Test
    @DisplayName("1 首次登记 expected=0 → 200 active revision=1；DB 行含账号/会话/注册（整数 schema_version）")
    void firstRegistrationCreatesActiveRow() throws Exception {
        String phone = newPhone();
        String installation = "inst-first";
        LoginResult login = loginAppWithInstallation(phone, installation);

        MvcResult r = putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok-1"), "0"), "k-" + UUID.randomUUID());
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("active", data(r).path("status").asText());
        assertEquals("1", data(r).path("destinationRevision").asText());
        assertNotNull(data(r).path("destinationId").asText(null));
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));

        Dest dest = destOf(installation);
        assertNotNull(dest);
        assertEquals(UUID.fromString(login.accountId()), dest.accountId());
        assertEquals(1L, dest.revision());
        assertEquals(PROVIDER, dest.provider());
        assertEquals(PLATFORM, dest.platform());
        assertEquals("active", dest.status());
        assertNotNull(dest.sessionRef());
        assertEquals("1", jdbc.queryForObject("SELECT registration ->> 'schema_version'"
                + " FROM notification_destinations WHERE installation_id = ?", String.class,
                installation));
        assertEquals("number", jdbc.queryForObject("SELECT jsonb_typeof(registration ->"
                + " 'schema_version') FROM notification_destinations WHERE installation_id = ?",
                String.class, installation));
        assertFalse(dest.invalidated());
        assertNotNull(jdbc.queryForObject("SELECT last_registered_at FROM notification_destinations"
                + " WHERE installation_id = ?", java.sql.Timestamp.class, installation));
    }

    // ---------------- 2. response minimal ----------------

    @Test
    @DisplayName("2 响应体只含 destinationId/destinationRevision/status（绝不回传推送 token）")
    void responseContainsOnlyThreeFields() throws Exception {
        String installation = "inst-fields";
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        MvcResult r = putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("secret-token-value"), "0"),
                "k-" + UUID.randomUUID());
        assertEquals(200, r.getResponse().getStatus());

        JsonNode d = data(r);
        Set<String> fieldNames = StreamSupport.stream(
                        ((Iterable<String>) () -> d.fieldNames()).spliterator(), false)
                .collect(Collectors.toSet());
        assertEquals(Set.of("destinationId", "destinationRevision", "status"), fieldNames);
        assertFalse(r.getResponse().getContentAsString().contains("secret-token-value"));
    }

    // ---------------- 3. same content / session refresh ----------------

    @Test
    @DisplayName("3 相同内容：同会话纯幂等不增代次；新会话重登记 → session_ref 刷新且代次 +1")
    void sameContentIdempotentVsSessionRefresh() throws Exception {
        String phone = newPhone();
        String installation = "inst-same";
        LoginResult first = loginAppWithInstallation(phone, installation);
        String firstSession = sessionIdOf(first.accessToken());

        MvcResult created = putJson(first.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok"), "0"), "k-" + UUID.randomUUID());
        assertEquals(200, created.getResponse().getStatus());
        assertEquals(firstSession, destOf(installation).sessionRef());

        // 纯幂等重登记：同会话 + 已 active + 相同内容 → 不递增代次
        MvcResult idempotent = putJson(first.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok"), "1"), "k-" + UUID.randomUUID());
        assertEquals(200, idempotent.getResponse().getStatus(),
                idempotent.getResponse().getContentAsString());
        assertEquals("1", data(idempotent).path("destinationRevision").asText());
        assertEquals(1L, destOf(installation).revision(),
                "纯幂等重登记（同 session、已 active）不得递增 destination_revision");
        assertEquals(firstSession, destOf(installation).sessionRef());

        // 同一账号重新登录（新会话），相同内容 + 当前代次 → 会话变化必须递增代次
        LoginResult second = loginAppWithInstallation(phone, installation);
        String secondSession = sessionIdOf(second.accessToken());
        assertNotEquals(firstSession, secondSession);

        MvcResult updated = putJson(second.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok"), "1"), "k-" + UUID.randomUUID());
        assertEquals(200, updated.getResponse().getStatus(), updated.getResponse().getContentAsString());
        assertEquals("2", data(updated).path("destinationRevision").asText(),
                "同内容但 session_ref 变化必须递增代次");
        Dest dest = destOf(installation);
        assertEquals(2L, dest.revision(), "session_ref 变化必须递增 destination_revision");
        assertEquals(secondSession, dest.sessionRef(), "session_ref 必须刷新为当前会话");
    }

    @Test
    @DisplayName("3b invalid 行同内容重新激活 → 200 active 且代次 +1，不复用旧 revision")
    void reactivatingInvalidDestinationBumpsRevision() throws Exception {
        String installation = "inst-reactivate";
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        assertEquals(200, putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok"), "0"), "k-" + UUID.randomUUID())
                .getResponse().getStatus());

        // 模拟登出失效（A 的 AuthController 把 session_ref 匹配行置 invalid）。
        jdbc.update("UPDATE notification_destinations SET status = 'invalid',"
                + " invalidated_at = now(), updated_at = now() WHERE installation_id = ?",
                installation);
        Dest before = destOf(installation);
        assertEquals("invalid", before.status());

        MvcResult r = putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok"), String.valueOf(before.revision())),
                "k-" + UUID.randomUUID());
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals(String.valueOf(before.revision() + 1),
                data(r).path("destinationRevision").asText(),
                "invalid 重新激活必须递增代次，不复用旧 revision");
        Dest after = destOf(installation);
        assertEquals(before.revision() + 1, after.revision(),
                "invalid → active 必须递增 destination_revision");
        assertEquals("active", after.status());
        assertFalse(after.invalidated());
    }

    // ---------------- 4. changed content bumps revision ----------------

    @Test
    @DisplayName("4 内容变化 → 200 且 destination_revision +1")
    void changedContentBumpsRevision() throws Exception {
        String installation = "inst-change";
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        assertEquals(200, putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("a"), "0"), "k-" + UUID.randomUUID())
                .getResponse().getStatus());

        MvcResult r = putJson(login.accessToken(), installation,
                body("dev-huawei", PLATFORM, registration("b"), "1"), "k-" + UUID.randomUUID());
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("2", data(r).path("destinationRevision").asText());
        Dest dest = destOf(installation);
        assertEquals(2L, dest.revision());
        assertEquals("dev-huawei", dest.provider());
    }

    // ---------------- 5. stale expected revision ----------------

    @Test
    @DisplayName("5 expectedDestinationRevision 不符 → 409 BINDING_CHANGED，details 只含 currentDestinationRevision，T09 未变")
    void staleExpectedRevisionConflicts() throws Exception {
        String installation = "inst-stale";
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        assertEquals(200, putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok"), "0"), "k-" + UUID.randomUUID())
                .getResponse().getStatus());
        Dest before = destOf(installation);

        MvcResult r = putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok"), "0"), "k-" + UUID.randomUUID());
        assertEquals(409, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("BINDING_CHANGED", error(r).path("code").asText());
        JsonNode details = error(r).path("details");
        Set<String> detailFields = StreamSupport.stream(
                        ((Iterable<String>) () -> details.fieldNames()).spliterator(), false)
                .collect(Collectors.toSet());
        assertEquals(Set.of("currentDestinationRevision"), detailFields);
        assertEquals("1", details.path("currentDestinationRevision").asText());

        Dest after = destOf(installation);
        assertEquals(before.revision(), after.revision());
        assertEquals(before.sessionRef(), after.sessionRef());
        assertEquals(before.status(), after.status());
    }

    // ---------------- 6. account switch ----------------

    @Test
    @DisplayName("6 换号（SC-01-17）：同 installationId 由 B 登录登记 → account 变 B、revision +1、旧快照失配")
    void accountSwitchTakesOverAndBumpsRevision() throws Exception {
        String installation = "inst-switch";
        LoginResult loginA = loginAppWithInstallation(newPhone(), installation);
        assertEquals(200, putJson(loginA.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("a"), "0"), "k-" + UUID.randomUUID())
                .getResponse().getStatus());
        long oldRevision = destOf(installation).revision();
        assertEquals(UUID.fromString(loginA.accountId()), destOf(installation).accountId());

        LoginResult loginB = loginAppWithInstallation(newPhone(), installation);
        MvcResult r = putJson(loginB.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("b"), "0"), "k-" + UUID.randomUUID());
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());

        Dest dest = destOf(installation);
        assertEquals(UUID.fromString(loginB.accountId()), dest.accountId());
        assertEquals(oldRevision + 1, dest.revision());
        assertEquals("active", dest.status());
        assertNotEquals(String.valueOf(dest.revision()), String.valueOf(oldRevision),
                "账号切换必须递增代次，使账号 A 的旧路由快照失配");
    }

    // ---------------- 7. authorization / invalid subjects ----------------

    @Test
    @DisplayName("7 越权/无效主体：installationId 不符 403 / 云台 403 / 无 token 401 / 伪造字段 400 / ios 400 / 空注册 400 / 缺 key 400")
    void authorizationMatrix() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-auth");
        String json = body(PROVIDER, PLATFORM, registration("tok"), "0");

        MvcResult mismatch = putJson(login.accessToken(), "inst-other", json,
                "k-" + UUID.randomUUID());
        assertEquals(403, mismatch.getResponse().getStatus());
        assertEquals("CALLER_NOT_ALLOWED", error(mismatch).path("code").asText());
        assertEquals(0, destCount("inst-other"));

        UUID gimbalId = seedGimbal();
        String gimbalToken = gimbalToken(gimbalId);
        MvcResult gimbal = putJson(gimbalToken, "inst-auth", json, "k-" + UUID.randomUUID());
        assertEquals(403, gimbal.getResponse().getStatus());
        assertEquals("CALLER_NOT_ALLOWED", error(gimbal).path("code").asText());
        assertEquals(0, destCount("inst-auth"));

        MvcResult anon = putJson(null, "inst-auth", json, "k-" + UUID.randomUUID());
        assertEquals(401, anon.getResponse().getStatus());
        assertEquals("AUTH_REQUIRED", error(anon).path("code").asText());
        assertEquals(0, destCount("inst-auth"));

        MvcResult forged = putJson(login.accessToken(), "inst-auth",
                JSON.writeValueAsString(Map.of("provider", PROVIDER, "platform", PLATFORM,
                        "registration", registration("tok"), "expectedDestinationRevision", "0",
                        "accountId", UUID.randomUUID().toString())),
                "k-" + UUID.randomUUID());
        assertEquals(400, forged.getResponse().getStatus(), forged.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", error(forged).path("code").asText());

        assertEquals(400, putJson(login.accessToken(), "inst-auth",
                body(PROVIDER, "ios", registration("tok"), "0"), "k-" + UUID.randomUUID())
                .getResponse().getStatus());
        assertEquals(400, putJson(login.accessToken(), "inst-auth",
                body(PROVIDER, PLATFORM, Map.of(), "0"), "k-" + UUID.randomUUID())
                .getResponse().getStatus());
        assertEquals(400, putJson(login.accessToken(), "inst-auth",
                body(PROVIDER, PLATFORM, registration("tok"), "0"), null)
                .getResponse().getStatus());
        assertEquals(400, putJson(login.accessToken(), "inst-auth",
                body(PROVIDER, PLATFORM, registration("tok"), "00"), "k-" + UUID.randomUUID())
                .getResponse().getStatus());
        assertEquals(0, destCount("inst-auth"));
    }

    // ---------------- 8. idempotency ----------------

    @Test
    @DisplayName("8 幂等：同键同内容重放 → meta.replayed=true 且 revision 不再增；同键不同内容 → 409")
    void idempotencyReplayAndConflict() throws Exception {
        String installation = "inst-idem";
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        String key = "k-idem-" + UUID.randomUUID();
        String json = body(PROVIDER, PLATFORM, registration("tok"), "0");

        MvcResult first = putJson(login.accessToken(), installation, json, key);
        assertEquals(200, first.getResponse().getStatus());
        assertFalse(JSON.readTree(first.getResponse().getContentAsString())
                .path("meta").path("replayed").asBoolean());

        MvcResult replay = putJson(login.accessToken(), installation, json, key);
        assertEquals(200, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        assertTrue(JSON.readTree(replay.getResponse().getContentAsString())
                .path("meta").path("replayed").asBoolean());
        assertEquals("1", data(replay).path("destinationRevision").asText());
        assertEquals(1L, destOf(installation).revision());

        MvcResult conflict = putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("different"), "0"), key);
        assertEquals(409, conflict.getResponse().getStatus(), conflict.getResponse().getContentAsString());
        assertEquals("IDEMPOTENCY_CONTENT_CONFLICT", error(conflict).path("code").asText());
        assertEquals(1L, destOf(installation).revision());
    }

    // ---------------- 9. concurrent first registration ----------------

    @Test
    @DisplayName("9 并发首建（两线程同 installationId 同账号 expected=0）→ 恰好 1 行，无 500")
    void concurrentFirstRegistrationSingleRow() throws Exception {
        String installation = "inst-race";
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        String json = body(PROVIDER, PLATFORM, registration("tok"), "0");

        int workers = 2;
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch go = new CountDownLatch(1);
        List<Future<Integer>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < workers; i++) {
                final String key = "k-race-" + i + "-" + UUID.randomUUID();
                futures.add(pool.submit((Callable<Integer>) () -> {
                    ready.countDown();
                    assertTrue(go.await(10, TimeUnit.SECONDS));
                    MvcResult r = putJson(login.accessToken(), installation, json, key);
                    if (r.getResponse().getStatus() == 500) {
                        throw new AssertionError("concurrent first registration returned 500: "
                                + r.getResponse().getContentAsString());
                    }
                    return r.getResponse().getStatus();
                }));
            }
            assertTrue(ready.await(10, TimeUnit.SECONDS));
            go.countDown();
            for (Future<Integer> f : futures) {
                int status = f.get(30, TimeUnit.SECONDS);
                assertTrue(status == 200 || status == 409, "unexpected status " + status);
            }
        } finally {
            pool.shutdownNow();
        }
        assertEquals(1, destCount(installation));
        assertEquals(1L, destOf(installation).revision());
    }

    // ---------------- 10. revoked session ----------------

    @Test
    @DisplayName("10 会话失效后 PUT → 401，T09 在该次 PUT 前后未变")
    void revokedSessionRejected() throws Exception {
        String installation = "inst-revoked";
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        assertEquals(200, putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("tok"), "0"), "k-" + UUID.randomUUID())
                .getResponse().getStatus());

        MvcResult logout = mockMvc.perform(delete("/api/v1/auth/sessions/current")
                .header("Authorization", "Bearer " + login.accessToken())).andReturn();
        assertEquals(204, logout.getResponse().getStatus());

        Dest before = destOf(installation);
        MvcResult r = putJson(login.accessToken(), installation,
                body(PROVIDER, PLATFORM, registration("new"), "1"), "k-" + UUID.randomUUID());
        assertEquals(401, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        Dest after = destOf(installation);
        assertEquals(before.revision(), after.revision());
        assertEquals(before.status(), after.status());
        assertEquals(before.sessionRef(), after.sessionRef());
    }
}

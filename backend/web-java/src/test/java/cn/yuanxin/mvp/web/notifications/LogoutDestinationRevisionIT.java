package cn.yuanxin.mvp.web.notifications;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

/**
 * 登出使 T09 通知目标失效时的代次语义（B 公共集成修复）：
 * 失效与 {@code destination_revision + 1} 在<b>同一条原子 UPDATE</b> 内完成，
 * 使该会话遗留的 T10 路由快照（建单时锁定旧代次）失配、旧任务不得写回；
 * 仅 {@code status='active'} 的真实变更行受影响（重复/并发登出幂等）；
 * HTTP 登出响应仍为 204 无体。真实 PG。
 */
class LogoutDestinationRevisionIT extends AbstractWebIT {

    private static final String PROVIDER = "dev-fcm";
    private static final String PLATFORM = "android";

    @Autowired
    JdbcTemplate jdbc;

    private record Dest(UUID id, UUID accountId, long revision, String status,
                        String sessionRef, Timestamp invalidatedAt) {
    }

    private static String body(String expected) throws Exception {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("provider", PROVIDER);
        m.put("platform", PLATFORM);
        m.put("registration", Map.of("token", "tok"));
        m.put("expectedDestinationRevision", expected);
        return JSON.writeValueAsString(m);
    }

    private MvcResult register(String token, String installation, String expected) throws Exception {
        return mockMvc.perform(put("/api/v1/me/notification-destinations/" + installation)
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", "k-" + UUID.randomUUID())
                        .contentType("application/json")
                        .content(body(expected)))
                .andReturn();
    }

    private MvcResult logout(String token) throws Exception {
        return mockMvc.perform(delete("/api/v1/auth/sessions/current")
                .header("Authorization", "Bearer " + token)).andReturn();
    }

    private Dest destOf(String installation) {
        List<Dest> rows = jdbc.query("SELECT id, account_id, destination_revision, status,"
                        + " session_ref, invalidated_at FROM notification_destinations"
                        + " WHERE installation_id = ?",
                (rs, i) -> new Dest(rs.getObject("id", UUID.class),
                        rs.getObject("account_id", UUID.class), rs.getLong("destination_revision"),
                        rs.getString("status"), rs.getString("session_ref"),
                        rs.getTimestamp("invalidated_at")),
                installation);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private static String uniq(String prefix) {
        return prefix + "-" + UUID.randomUUID().toString().substring(0, 8);
    }

    private UUID seedGimbal() {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                        + " VALUES (?, ?, ?, 1)",
                id, "gimbal-logout-" + id, "cred-" + id);
        return id;
    }

    // ---------------- 1. invalid + revision exactly +1 + 204 no body ----------------

    @Test
    @DisplayName("登出：T09 行 invalid + invalidated_at 非空 + destination_revision 恰好 +1；响应 204 无体")
    void logoutInvalidatesAndBumpsRevisionExactlyOnce() throws Exception {
        String installation = uniq("inst-logout-bump");
        LoginResult login = loginAppWithInstallation(newPhone(), installation);

        MvcResult created = register(login.accessToken(), installation, "0");
        assertEquals(200, created.getResponse().getStatus(), created.getResponse().getContentAsString());

        Dest before = destOf(installation);
        assertNotNull(before);
        assertEquals("active", before.status());
        assertEquals(1L, before.revision());
        assertNotNull(before.sessionRef());
        assertNull(before.invalidatedAt());

        MvcResult out = logout(login.accessToken());
        assertEquals(204, out.getResponse().getStatus());
        assertEquals("", out.getResponse().getContentAsString(), "登出必须 204 且无响应体");

        Dest after = destOf(installation);
        assertEquals("invalid", after.status());
        assertNotNull(after.invalidatedAt(), "invalidated_at 必须被设置");
        assertEquals(before.revision() + 1, after.revision(),
                "失效与代次递增须在同一条 UPDATE：恰好 +1，使旧 T10 快照失配");
        assertEquals(before.sessionRef(), after.sessionRef(), "失效不改变 session_ref 归属");
    }

    // ---------------- 2. idempotency of repeated / already-invalid ----------------

    @Test
    @DisplayName("重复登出幂等：同 token 再登出 401 且不再递增/不刷新 invalidated_at；已 invalid 行不被二次递增")
    void repeatedLogoutIsIdempotent() throws Exception {
        // (a) 同 token 再登出：撤销已生效 → 401，T09 不再变化
        String installation = uniq("inst-logout-repeat");
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        assertEquals(200, register(login.accessToken(), installation, "0").getResponse().getStatus());
        assertEquals(204, logout(login.accessToken()).getResponse().getStatus());

        Dest afterFirst = destOf(installation);
        assertEquals(2L, afterFirst.revision());
        Timestamp firstInvalidatedAt = afterFirst.invalidatedAt();
        assertNotNull(firstInvalidatedAt);

        MvcResult second = logout(login.accessToken());
        assertEquals(401, second.getResponse().getStatus(), second.getResponse().getContentAsString());

        Dest afterSecond = destOf(installation);
        assertEquals(afterFirst.revision(), afterSecond.revision(), "重复登出不得再次递增代次");
        assertEquals(firstInvalidatedAt, afterSecond.invalidatedAt(), "重复登出不得刷新 invalidated_at");

        // (b) 已 invalid 但会话仍 active 的行：失效语句只命中 status='active' → 0 行受影响，
        //     直接验证 WHERE 守卫（不依赖第二次 401 短路），不递增、不刷新 invalidated_at。
        String installation2 = uniq("inst-logout-already-invalid");
        LoginResult login2 = loginAppWithInstallation(newPhone(), installation2);
        assertEquals(200, register(login2.accessToken(), installation2, "0").getResponse().getStatus());
        Timestamp staleInvalidatedAt = Timestamp.from(Instant.parse("2026-01-01T00:00:00Z"));
        jdbc.update("UPDATE notification_destinations SET status='invalid', invalidated_at=?,"
                        + " updated_at=now() WHERE installation_id=?",
                staleInvalidatedAt, installation2);

        assertEquals(204, logout(login2.accessToken()).getResponse().getStatus());

        Dest row2 = destOf(installation2);
        assertEquals("invalid", row2.status());
        assertEquals(1L, row2.revision(), "已 invalid 行不得因登出被二次递增");
        assertEquals(staleInvalidatedAt, row2.invalidatedAt(), "已 invalid 行不得刷新 invalidated_at");
    }

    // ---------------- 3. stale T10 route snapshot blocked ----------------

    @Test
    @DisplayName("旧任务写回阻断：T10 快照锁定登出前代次，登出后 T09 代次 +1 → 失配，守卫写回 0 行")
    void logoutBlocksStaleT10WriteBack() throws Exception {
        String installation = uniq("inst-logout-t10");
        LoginResult login = loginAppWithInstallation(newPhone(), installation);
        assertEquals(200, register(login.accessToken(), installation, "0").getResponse().getStatus());

        Dest snapshotted = destOf(installation);
        UUID gimbalId = seedGimbal();
        UUID notificationId = UUID.randomUUID();
        // T10 路由快照：建单时锁定当时的 T09 代次与目标
        jdbc.update("INSERT INTO notifications (id, gimbal_id, incident_id, event_type, account_id,"
                        + " binding_revision, destination_id, destination_revision, payload, status)"
                        + " VALUES (?, ?, ?, 'anomaly', ?::uuid, 1, ?, ?,"
                        + " '{\"schema_version\":1}'::jsonb, 'pending')",
                notificationId, gimbalId, "incident-" + notificationId, login.accountId(),
                snapshotted.id(), snapshotted.revision());

        assertEquals(204, logout(login.accessToken()).getResponse().getStatus());
        Dest current = destOf(installation);
        assertEquals(snapshotted.revision() + 1, current.revision());

        long snap = jdbc.queryForObject(
                "SELECT destination_revision FROM notifications WHERE id = ?",
                Long.class, notificationId);
        assertNotEquals(current.revision(), snap,
                "T10 快照代次必须与登出后的 T09 当前代次失配"
                        + "（Python 侧据此 route_recheck_failed 取消投递）");

        // 旧任务按"快照代次 == T09 当前代次"守卫写回 → 0 行，通知不得离开 pending
        int writtenBack = jdbc.update("UPDATE notifications n"
                        + " SET status='submitted', last_attempt_at=now()"
                        + " WHERE n.id = ? AND n.status = 'pending'"
                        + " AND n.destination_revision = (SELECT d.destination_revision"
                        + " FROM notification_destinations d WHERE d.id = n.destination_id)",
                notificationId);
        assertEquals(0, writtenBack, "代次失配时旧任务不得写回通知");
        assertEquals("pending", jdbc.queryForObject(
                "SELECT status FROM notifications WHERE id = ?", String.class, notificationId));
    }

    // ---------------- 4. re-registration after logout keeps incrementing ----------------

    @Test
    @DisplayName("登出后重新登记：同 installation 新会话 → 200 active，代次在失效代次之上继续递增")
    void reRegisterAfterLogoutContinuesRevision() throws Exception {
        String phone = newPhone();
        String installation = uniq("inst-logout-re-reg");
        LoginResult first = loginAppWithInstallation(phone, installation);
        assertEquals(200, register(first.accessToken(), installation, "0").getResponse().getStatus());
        assertEquals(204, logout(first.accessToken()).getResponse().getStatus());

        Dest invalid = destOf(installation);
        assertEquals("invalid", invalid.status());
        long invalidRevision = invalid.revision();

        LoginResult second = loginAppWithInstallation(phone, installation);
        String secondSession = sessionIdOf(second.accessToken());
        MvcResult re = register(second.accessToken(), installation, String.valueOf(invalidRevision));
        assertEquals(200, re.getResponse().getStatus(), re.getResponse().getContentAsString());
        assertEquals(String.valueOf(invalidRevision + 1),
                JSON.readTree(re.getResponse().getContentAsString())
                        .path("data").path("destinationRevision").asText());

        Dest active = destOf(installation);
        assertEquals("active", active.status());
        assertEquals(invalidRevision + 1, active.revision(), "重新激活必须在失效代次之上继续递增");
        assertEquals(secondSession, active.sessionRef());
        assertNull(active.invalidatedAt());
        assertTrue(active.revision() > invalidRevision);
    }
}

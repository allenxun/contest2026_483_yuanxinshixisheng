package cn.yuanxin.mvp.web.auth;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

/**
 * 认证基础面（digest §6 验收）：无效认证拒绝、替身签发 token 的主体上下文、
 * 手机号会话全链路（挑战→登录→再登录同账号→刷新→撤销→T09 目标失效）、
 * 云台设备会话（gimbals 行 SQL 种子验证）。
 */
class AuthFlowIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    @DisplayName("受保护端点无 token → 401 AUTH_REQUIRED（业务 stub 路径同样先 401）")
    void missingTokenIs401() throws Exception {
        MvcResult r = mockMvc.perform(get("/api/v1/me/member-access-grants")).andReturn();
        assertEquals(401, r.getResponse().getStatus());
        JsonNode body = JSON.readTree(r.getResponse().getContentAsString());
        assertEquals("AUTH_REQUIRED", body.path("error").path("code").asText());
        assertNotNull(r.getResponse().getHeader("X-Request-Id"));
    }

    @Test
    @DisplayName("任意伪造/垃圾 token → 401 SESSION_INVALID；绝不凭自报身份认证成功")
    void garbageTokenIs401() throws Exception {
        for (String token : List.of("garbage-token", "accountId=anything", "nothing")) {
            MvcResult r = mockMvc.perform(get("/api/v1/system/echo-jobs/" + UUID.randomUUID())
                            .header("Authorization", "Bearer " + token.replace("Bearer ", "")))
                    .andReturn();
            assertEquals(401, r.getResponse().getStatus(), token);
            assertEquals("SESSION_INVALID",
                    JSON.readTree(r.getResponse().getContentAsString())
                            .path("error").path("code").asText());
        }
    }

    @Test
    @DisplayName("请求体声明 accountId 不被信任：未知字段直接 400；身份只来自 token")
    void bodyDeclaredIdentityNeverTrusted() throws Exception {
        String token = loginApp(newPhone());
        // 声称自己是别的账号（未知字段 → 400；即便未来字段合法，principal 也来自 token）
        MvcResult r = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json")
                        .content("{\"message\":\"x\",\"numbersAsStrings\":[],\"accountId\":\""
                                + UUID.randomUUID() + "\"}"))
                .andReturn();
        assertEquals(400, r.getResponse().getStatus());
        assertEquals("INVALID_INPUT",
                JSON.readTree(r.getResponse().getContentAsString())
                        .path("error").path("code").asText());
    }

    @Test
    @DisplayName("替身签发的 token → PrincipalContext 正确（经 T13 行断言 principal 格式）")
    void doubleIssuedTokenPrincipal() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-principal-1");
        String key = "key-principal-" + UUID.randomUUID();
        MvcResult r = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + login.accessToken())
                        .header("Idempotency-Key", key)
                        .contentType("application/json")
                        .content("{\"message\":\"principal\",\"numbersAsStrings\":[\"7\"]}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        List<String> principals = jdbc.queryForList(
                "SELECT principal_type || '|' || principal_id FROM idempotency_requests"
                        + " WHERE operation = 'system.echo.create' AND idempotency_key = ?",
                String.class, key);
        assertEquals(1, principals.size());
        assertEquals("app_account", principals.get(0).split("\\|")[0]);
        String pid = principals.get(0).split("\\|")[1];
        String[] parts = pid.split(":", 2);
        assertEquals(login.accountId(), parts[0]);
        assertEquals("inst-principal-1", parts[1]);
    }

    @Test
    @DisplayName("手机号会话全链路：登录/再登录同账号/刷新/撤销/T09 目标失效/旧 token 401")
    void fullSmsSessionLifecycle() throws Exception {
        String phone = newPhone();
        LoginResult first = loginAppWithInstallation(phone, "inst-lifecycle");
        String accountId = first.accountId();

        Integer rows = jdbc.queryForObject("SELECT count(*) FROM accounts WHERE id = ?::uuid",
                Integer.class, accountId);
        assertEquals(1, rows);
        assertEquals("phone", jdbc.queryForObject(
                "SELECT login_provider FROM accounts WHERE id = ?::uuid", String.class, accountId));
        assertEquals(phone, jdbc.queryForObject(
                "SELECT login_subject FROM accounts WHERE id = ?::uuid", String.class, accountId));

        // 第二次登录同手机号 → 同一账号、仅一行
        LoginResult second = loginAppWithInstallation(phone, "inst-lifecycle");
        assertEquals(accountId, second.accountId());
        rows = jdbc.queryForObject("SELECT count(*) FROM accounts WHERE login_provider='phone'"
                + " AND login_subject = ?", Integer.class, phone);
        assertEquals(1, rows);

        // 刷新：新 token 可用、旧 access token 失效
        MvcResult fr = mockMvc.perform(post("/api/v1/auth/session-refreshes")
                        .contentType("application/json")
                        .content("{\"refreshCredential\":\"" + second.refreshToken() + "\"}"))
                .andReturn();
        assertEquals(200, fr.getResponse().getStatus(), fr.getResponse().getContentAsString());
        JsonNode fdata = JSON.readTree(fr.getResponse().getContentAsString()).path("data");
        String refreshedToken = fdata.path("accessToken").asText();
        assertEquals(accountId, fdata.path("accountId").asText());
        MvcResult oldTok = mockMvc.perform(get("/api/v1/system/echo-jobs/" + UUID.randomUUID())
                        .header("Authorization", "Bearer " + second.accessToken()))
                .andReturn();
        assertEquals(401, oldTok.getResponse().getStatus());
        MvcResult newTok = mockMvc.perform(get("/api/v1/system/echo-jobs/" + UUID.randomUUID())
                        .header("Authorization", "Bearer " + refreshedToken))
                .andReturn();
        assertTrue(newTok.getResponse().getStatus() == 404 || newTok.getResponse().getStatus() == 200);

        // T09：登记一个绑定当前（刷新后）会话的推送目标，退出必须按 session_ref 失效
        String sessionRef = sessionIdOf(refreshedToken);
        assertNotNull(sessionRef);
        jdbc.update("INSERT INTO notification_destinations (id, installation_id, account_id,"
                        + " destination_revision, status, session_ref, registration)"
                        + " VALUES (?::uuid, 'inst-lifecycle', ?::uuid, 1, 'active', ?,"
                        + " '{\"schema_version\":1,\"token\":\"t1\"}'::jsonb)",
                UUID.randomUUID().toString(), accountId, sessionRef);
        jdbc.update("INSERT INTO notification_destinations (id, installation_id, account_id,"
                        + " destination_revision, status, session_ref, registration)"
                        + " VALUES (?::uuid, 'inst-other-device', ?::uuid, 1, 'active', 'other-session',"
                        + " '{\"schema_version\":1,\"token\":\"t2\"}'::jsonb)",
                UUID.randomUUID().toString(), accountId);

        // 退出：204；该 session_ref 的 T09 目标 invalid；其他安装实例不受影响
        MvcResult dr = mockMvc.perform(delete("/api/v1/auth/sessions/current")
                        .header("Authorization", "Bearer " + refreshedToken))
                .andReturn();
        assertEquals(204, dr.getResponse().getStatus());
        String status = jdbc.queryForObject("SELECT status FROM notification_destinations"
                + " WHERE installation_id = 'inst-lifecycle'", String.class);
        assertEquals("invalid", status);
        String other = jdbc.queryForObject("SELECT status FROM notification_destinations"
                + " WHERE installation_id = 'inst-other-device'", String.class);
        assertEquals("active", other);
        MvcResult revoked = mockMvc.perform(get("/api/v1/system/echo-jobs/" + UUID.randomUUID())
                        .header("Authorization", "Bearer " + refreshedToken))
                .andReturn();
        assertEquals(401, revoked.getResponse().getStatus());
    }

    @Test
    @DisplayName("云台设备会话：SQL 种子凭据正确→token；错误凭据/版本→401；token 主体=gimbal")
    void gimbalDeviceSession() throws Exception {
        String serial = "SN-IT-" + UUID.randomUUID().toString().substring(0, 8);
        String authRef = "authref-" + serial;
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                + " VALUES (?::uuid, ?, ?, 3)", UUID.randomUUID().toString(), serial, authRef);
        String gimbalId = jdbc.queryForObject("SELECT id::text FROM gimbals WHERE serial_no = ?",
                String.class, serial);

        MvcResult ok = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + authRef + "\","
                                + "\"credentialVersion\":\"3\",\"proof\":\"p1\"}"))
                .andReturn();
        assertEquals(200, ok.getResponse().getStatus(), ok.getResponse().getContentAsString());
        JsonNode data = JSON.readTree(ok.getResponse().getContentAsString()).path("data");
        assertEquals(gimbalId, data.path("gimbalId").asText());
        String gimbalToken = data.path("sessionToken").asText();

        // 错误凭据 / 版本不符：统一 401 AUTH_REQUIRED（防枚举，见类文档）
        for (String body : List.of(
                "{\"credential\":\"bogus\",\"credentialVersion\":\"3\",\"proof\":\"p\"}",
                "{\"credential\":\"" + authRef + "\",\"credentialVersion\":\"2\",\"proof\":\"p\"}")) {
            MvcResult bad = mockMvc.perform(post("/api/v1/gimbal-sessions")
                    .contentType("application/json").content(body)).andReturn();
            assertEquals(401, bad.getResponse().getStatus());
            assertEquals("AUTH_REQUIRED", JSON.readTree(bad.getResponse().getContentAsString())
                    .path("error").path("code").asText());
        }

        // 云台 token 走业务 stub：已认证 → 501；principal 格式 = gimbal|<gimbal_uuid>
        MvcResult stub = mockMvc.perform(put("/api/v1/me/notification-destinations/inst-x")
                        .header("Authorization", "Bearer " + gimbalToken)
                        .contentType("application/json").content("{}"))
                .andReturn();
        assertEquals(501, stub.getResponse().getStatus());

        MvcResult echo = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + gimbalToken)
                        .header("Idempotency-Key", "gimbal-key-" + UUID.randomUUID())
                        .contentType("application/json")
                        .content("{\"message\":\"from-gimbal\",\"numbersAsStrings\":[\"0\"]}"))
                .andReturn();
        assertEquals(200, echo.getResponse().getStatus(), echo.getResponse().getContentAsString());
        List<String> principal = jdbc.queryForList(
                "SELECT principal_type || '|' || principal_id FROM idempotency_requests"
                        + " WHERE operation='system.echo.create' AND principal_id = ?",
                String.class, gimbalId);
        assertEquals(1, principal.size());
        assertEquals("gimbal|" + gimbalId, principal.get(0));
    }
}

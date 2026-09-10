package cn.yuanxin.mvp.web.auth;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * 认证状态实时复核（oracle B2）：会话签发后本地 T14/T03 状态变化必须立即
 * 使旧 token 失效——账号 disabled、auth_revision 递增（全端登出）、云台
 * credential_version 轮换；停用账号也不得经 create/refresh 续命。
 * BearerAuthFilter → PrincipalRevalidator 每请求单行查询，无 JOIN/锁。
 */
class RevocationIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    /** 已认证探测端点：token 有效时 404（未知 job），失效时 401 SESSION_INVALID。 */
    private MvcResult probe(String token) throws Exception {
        return mockMvc.perform(get("/api/v1/system/echo-jobs/" + UUID.randomUUID())
                .header("Authorization", "Bearer " + token)).andReturn();
    }

    @Test
    @DisplayName("会话中途停用账号 → 旧 token 401 SESSION_INVALID；refresh 也 401")
    void disabledAccountRevokesMidSession() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-rev-disable");
        assertEquals(404, probe(login.accessToken()).getResponse().getStatus()); // 签发前有效

        jdbc.update("UPDATE accounts SET status = 'disabled', auth_revision = auth_revision + 1,"
                + " disabled_at = now() WHERE id = ?::uuid", login.accountId());

        MvcResult r = probe(login.accessToken());
        assertEquals(401, r.getResponse().getStatus());
        JsonNode err = JSON.readTree(r.getResponse().getContentAsString());
        assertEquals("SESSION_INVALID", err.path("error").path("code").asText());

        MvcResult refresh = mockMvc.perform(post("/api/v1/auth/session-refreshes")
                        .contentType("application/json")
                        .content("{\"refreshCredential\":\"" + login.refreshToken()
                                + "\",\"installationId\":\"inst-rev-disable\"}"))
                .andReturn();
        assertEquals(401, refresh.getResponse().getStatus());
        assertEquals("SESSION_INVALID", JSON.readTree(refresh.getResponse().getContentAsString())
                .path("error").path("code").asText());
    }

    @Test
    @DisplayName("auth_revision 递增（全端登出协议）→ 旧 token 立即 401；重新登录可用")
    void authRevisionBumpRevokesTokens() throws Exception {
        String phone = newPhone();
        LoginResult first = loginAppWithInstallation(phone, "inst-rev-bump");
        jdbc.update("UPDATE accounts SET auth_revision = auth_revision + 1 WHERE id = ?::uuid",
                first.accountId());
        assertEquals(401, probe(first.accessToken()).getResponse().getStatus());

        // 新登录捕获新 revision → 正常
        LoginResult second = loginAppWithInstallation(phone, "inst-rev-bump");
        assertEquals(404, probe(second.accessToken()).getResponse().getStatus());
        // 旧会话仍失效（无副作用）
        assertEquals(401, probe(first.accessToken()).getResponse().getStatus());
    }

    @Test
    @DisplayName("R2-2 刷新不复活已撤销代次：login→bump auth_revision(status 仍 active)→原 refresh token→401；旧 access→401；新登录成功")
    void refreshDoesNotResurrectRevokedGeneration() throws Exception {
        String phone = newPhone();
        LoginResult login = loginAppWithInstallation(phone, "inst-gen-refresh");
        jdbc.update("UPDATE accounts SET auth_revision = auth_revision + 1 WHERE id = ?::uuid",
                login.accountId());
        // 账号仍 active，仅代次递增（模拟全端登出/撤销，而非停用）
        assertEquals("active", jdbc.queryForObject(
                "SELECT status FROM accounts WHERE id = ?::uuid", String.class, login.accountId()));

        MvcResult refresh = mockMvc.perform(post("/api/v1/auth/session-refreshes")
                        .contentType("application/json")
                        .content("{\"refreshCredential\":\"" + login.refreshToken()
                                + "\",\"installationId\":\"inst-gen-refresh\"}"))
                .andReturn();
        assertEquals(401, refresh.getResponse().getStatus(), refresh.getResponse().getContentAsString());
        assertEquals("SESSION_INVALID", JSON.readTree(refresh.getResponse().getContentAsString())
                .path("error").path("code").asText());
        // 旧 access token 仍失效
        assertEquals(401, probe(login.accessToken()).getResponse().getStatus());
        // 全新 SMS 登录捕获新代次 → 可用
        LoginResult fresh = loginAppWithInstallation(phone, "inst-gen-refresh");
        assertEquals(404, probe(fresh.accessToken()).getResponse().getStatus());
    }

    @Test
    @DisplayName("停用账号不能新建会话：sessions → 401 SESSION_INVALID（不给 token）")
    void disabledAccountCannotCreateSession() throws Exception {
        String phone = newPhone();
        LoginResult login = loginAppWithInstallation(phone, "inst-rev-create");
        jdbc.update("UPDATE accounts SET status = 'disabled', disabled_at = now() WHERE id = ?::uuid",
                login.accountId());

        MvcResult ch = mockMvc.perform(post("/api/v1/auth/sms-challenges")
                        .contentType("application/json")
                        .content("{\"phone\":\"" + phone + "\",\"purpose\":\"login\"}"))
                .andReturn();
        assertEquals(200, ch.getResponse().getStatus()); // 发码不查账号（无账号状态侧信道：只回 challengeId）
        String challengeId = JSON.readTree(ch.getResponse().getContentAsString())
                .path("data").path("challengeId").asText();
        MvcResult se = mockMvc.perform(post("/api/v1/auth/sessions")
                        .contentType("application/json")
                        .content("{\"challengeId\":\"" + challengeId + "\",\"code\":\"123456\","
                                + "\"installationId\":\"inst-rev-create\"}"))
                .andReturn();
        assertEquals(401, se.getResponse().getStatus());
        assertEquals("SESSION_INVALID", JSON.readTree(se.getResponse().getContentAsString())
                .path("error").path("code").asText());
    }

    @Test
    @DisplayName("云台 credential_version 轮换 → 旧云台 token 401 SESSION_INVALID")
    void gimbalCredentialRotationRevokesToken() throws Exception {
        String serial = "SN-REV-" + UUID.randomUUID().toString().substring(0, 8);
        String authRef = "authref-" + serial;
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                + " VALUES (?::uuid, ?, ?, 3)", UUID.randomUUID().toString(), serial, authRef);

        MvcResult gs = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + authRef + "\","
                                + "\"credentialVersion\":\"3\",\"proof\":\"p1\"}"))
                .andReturn();
        assertEquals(200, gs.getResponse().getStatus(), gs.getResponse().getContentAsString());
        String gimbalToken = JSON.readTree(gs.getResponse().getContentAsString())
                .path("data").path("sessionToken").asText();
        int before = probe(gimbalToken).getResponse().getStatus();
        assertTrue(before == 404 || before == 200, "轮换前云台 token 应可用，got " + before);

        jdbc.update("UPDATE gimbals SET credential_version = 4 WHERE serial_no = ?", serial);
        MvcResult after = probe(gimbalToken);
        assertEquals(401, after.getResponse().getStatus());
        assertEquals("SESSION_INVALID", JSON.readTree(after.getResponse().getContentAsString())
                .path("error").path("code").asText());
    }
}

package cn.yuanxin.mvp.web.devices;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * 测试组 1：M2-A01 云台认证（A 已实现，本 lane 只验证不修改）。
 *
 * <p>证明：合法凭据签发会话且不含成员资料；无效凭据/错 credentialVersion →
 * 401 且 T03 未被登记为在线；重复认证不创建护理执行/job/通知；credential_version
 * 递增后旧 token 立即失效；云台 token 可用于 A02/A03/A04/A05；认证不缓存
 * 凭据（带 Idempotency-Key 也不写 T13）。</p>
 */
class GimbalSessionVerificationIT extends AbstractDeviceIT {

    @Test
    @DisplayName("凭据失败不登记可信在线；成功签发不含成员资料")
    void validCredentialIssuesSessionWithoutMemberData() throws Exception {
        UUID gimbalId = seedGimbal(1L);
        Map<String, Object> before = jdbc.queryForMap(
                "SELECT last_seen_at, connection_status FROM gimbals WHERE id = ?", gimbalId);

        MvcResult ok = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + credentialOf(gimbalId)
                                + "\",\"credentialVersion\":\"1\",\"proof\":\"dev-proof\"}"))
                .andReturn();
        assertEquals(200, ok.getResponse().getStatus(), ok.getResponse().getContentAsString());
        JsonNode data = dataOf(ok);
        assertEquals(gimbalId.toString(), data.path("gimbalId").asText());
        assertFalse(data.path("sessionToken").asText().isBlank());
        assertNotNull(data.path("expiresAt").asText(null));
        assertNotNull(data.path("serverTime").asText(null));
        // 不返回任何成员/账号资料
        assertFalse(data.has("accountId"));
        assertFalse(data.has("memberId"));
        assertFalse(data.has("phone"));

        // 凭据失败（未知凭据 / 错 credentialVersion）→ 401，T03 原值不变
        MvcResult badCredential = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"ghost-credential\",\"credentialVersion\":\"1\","
                                + "\"proof\":\"dev-proof\"}"))
                .andReturn();
        assertEquals(401, badCredential.getResponse().getStatus());
        MvcResult badVersion = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + credentialOf(gimbalId)
                                + "\",\"credentialVersion\":\"99\",\"proof\":\"dev-proof\"}"))
                .andReturn();
        assertEquals(401, badVersion.getResponse().getStatus());

        Map<String, Object> after = jdbc.queryForMap(
                "SELECT last_seen_at, connection_status FROM gimbals WHERE id = ?", gimbalId);
        assertEquals(before, after);
        assertEquals("unknown", after.get("connection_status"));
    }

    @Test
    @DisplayName("重复认证不创建 care_executions/async_jobs/notifications")
    void repeatedAuthenticationCreatesNoCareResources() throws Exception {
        UUID gimbalId = seedGimbal(1L);
        long executions = count("care_executions", "1 = 1");
        long jobs = count("async_jobs", "1 = 1");
        long notifications = count("notifications", "1 = 1");

        for (int i = 0; i < 3; i++) {
            String token = gimbalToken(gimbalId, 1L);
            assertEquals(401, mockMvc.perform(post("/api/v1/gimbal-sessions")
                            .contentType("application/json")
                            .content("{\"credential\":\"nope\",\"credentialVersion\":\"1\","
                                    + "\"proof\":\"p\"}"))
                    .andReturn().getResponse().getStatus());
            assertFalse(token.isBlank());
        }

        assertEquals(executions, count("care_executions", "1 = 1"));
        assertEquals(jobs, count("async_jobs", "1 = 1"));
        assertEquals(notifications, count("notifications", "1 = 1"));
    }

    @Test
    @DisplayName("认证不使用 Idempotency-Key 缓存凭据")
    void authenticationDoesNotUseIdempotencyKey() throws Exception {
        UUID gimbalId = seedGimbal(1L);
        for (int i = 0; i < 2; i++) {
            MvcResult result = mockMvc.perform(post("/api/v1/gimbal-sessions")
                            .header("Idempotency-Key", "cred-" + gimbalId)
                            .contentType("application/json")
                            .content("{\"credential\":\"" + credentialOf(gimbalId)
                                    + "\",\"credentialVersion\":\"1\",\"proof\":\"dev-proof\"}"))
                    .andReturn();
            assertEquals(200, result.getResponse().getStatus());
        }
        assertEquals(0, count("idempotency_requests",
                "principal_type = 'gimbal' AND operation LIKE '%gimbal%'"));
    }

    @Test
    @DisplayName("云台 token 可用于 A02/A03/A04/A05；credential_version 递增后旧 token 401")
    void tokenUsableAcrossEndpointsAndRotationInvalidates() throws Exception {
        GimbalSession session = gimbalSession();
        String token = session.accessToken();
        UUID gimbalId = session.gimbalId();

        MvcResult heartbeat = mockMvc.perform(post("/api/v1/gimbals/" + gimbalId + "/heartbeats")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json")
                        .content(heartbeatJson("epoch-1", "1", "awake", null, null, null)))
                .andReturn();
        assertEquals(200, heartbeat.getResponse().getStatus(),
                heartbeat.getResponse().getContentAsString());
        assertTrue(dataOf(heartbeat).path("accepted").asBoolean());

        MvcResult status = mockMvc.perform(get("/api/v1/gimbals/" + gimbalId + "/status")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(200, status.getResponse().getStatus(), status.getResponse().getContentAsString());

        String serial = "mc-" + UUID.randomUUID();
        MvcResult observation = mockMvc.perform(post("/api/v1/microcrystal-observations")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", "obs-" + serial)
                        .contentType("application/json")
                        .content(observationJson(serial,
                                DevProofFixture.connectionGimbal(gimbalId, serial), "e1", "1")))
                .andReturn();
        assertEquals(200, observation.getResponse().getStatus(),
                observation.getResponse().getContentAsString());
        UUID microcrystalId = UUID.fromString(dataOf(observation).path("microcrystalId").asText());

        MvcResult capabilities = mockMvc.perform(get("/api/v1/microcrystals/" + microcrystalId
                        + "/capabilities").header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(200, capabilities.getResponse().getStatus(),
                capabilities.getResponse().getContentAsString());

        // credential_version 轮换：旧 token 立即失效（A 的 PrincipalRevalidator）。
        jdbc.update("UPDATE gimbals SET credential_version = 2 WHERE id = ?", gimbalId);
        MvcResult stale = mockMvc.perform(get("/api/v1/gimbals/" + gimbalId + "/status")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(401, stale.getResponse().getStatus(), stale.getResponse().getContentAsString());
        assertEquals("SESSION_INVALID", errorOf(stale).path("code").asText());
    }

    private static String observationJson(String serial, String proof, String epoch, String seq)
            throws Exception {
        return writeJson(Map.of(
                "microcrystalSerial", serial,
                "connectionProof", proof,
                "capabilities", Map.of("schemaVersion", 1, "revision", "1"),
                "observationEpoch", epoch,
                "observationSeq", seq,
                "observedAt", Instant.now().toString(),
                "state", Map.of("mode", "idle")));
    }
}

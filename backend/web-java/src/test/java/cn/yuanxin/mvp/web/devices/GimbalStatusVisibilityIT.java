package cn.yuanxin.mvp.web.devices;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * 测试组 7：M2-A03 访问范围与 isStale。
 *
 * <p>绑定账号 200、云台自身 200、其他账号/其他云台/不存在统一 404（error 体
 * 逐字一致）；isStale 在 lastSeenAt 空或超阈值时为 true；响应不含成员/账号资料。</p>
 */
class GimbalStatusVisibilityIT extends AbstractDeviceIT {

    private MvcResult status(String token, UUID gimbalId) throws Exception {
        return mockMvc.perform(get("/api/v1/gimbals/" + gimbalId + "/status")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
    }

    @Test
    @DisplayName("可见性、不可区分 404、isStale 与字段集")
    void visibilityAndStaleness() throws Exception {
        UUID gimbalId = seedGimbal();
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-status-owner");
        LoginResult stranger = loginAppWithInstallation(newPhone(), "inst-status-stranger");
        jdbc.update("UPDATE gimbals SET bound_account_id = ?, bound_at = now(),"
                + " binding_revision = 1 WHERE id = ?", UUID.fromString(owner.accountId()),
                gimbalId);

        GimbalSession self = new GimbalSession(gimbalId, credentialOf(gimbalId), 1L,
                gimbalToken(gimbalId, 1L));

        // 初始：从未心跳 → unknown / null / isStale=true
        MvcResult initial = status(owner.accessToken(), gimbalId);
        assertEquals(200, initial.getResponse().getStatus(), initial.getResponse().getContentAsString());
        JsonNode data = dataOf(initial);
        assertEquals("unknown", data.path("connectionStatus").asText());
        assertTrue(data.path("powerState").isNull());
        assertTrue(data.path("lastSeenAt").isNull());
        assertTrue(data.path("isStale").asBoolean());
        assertEquals("0", data.path("statusRevision").asText());
        assertTrue(data.path("incidents").isArray());
        assertEquals(Set.of("connectionStatus", "powerState", "lastSeenAt", "isStale",
                        "statusRevision", "incidents"),
                fieldNames(data));
        assertFalse(initial.getResponse().getContentAsString().contains(owner.accountId()));

        // 云台自身可读
        assertEquals(200, status(self.accessToken(), gimbalId).getResponse().getStatus());

        // 心跳后：online/awake/isStale=false
        mockMvc.perform(post("/api/v1/gimbals/" + gimbalId + "/heartbeats")
                        .header("Authorization", "Bearer " + self.accessToken())
                        .contentType("application/json")
                        .content(heartbeatJson("e", "1", "awake", null, null, null)))
                .andReturn();
        JsonNode afterHeartbeat = dataOf(status(owner.accessToken(), gimbalId));
        assertEquals("online", afterHeartbeat.path("connectionStatus").asText());
        assertEquals("awake", afterHeartbeat.path("powerState").asText());
        assertFalse(afterHeartbeat.path("isStale").asBoolean());
        assertFalse(afterHeartbeat.path("lastSeenAt").isNull());

        // 超阈值 → isStale=true
        jdbc.update("UPDATE gimbals SET last_seen_at = now() - interval '2 hours' WHERE id = ?",
                gimbalId);
        assertTrue(dataOf(status(owner.accessToken(), gimbalId)).path("isStale").asBoolean());

        // 其他账号 / 其他云台 / 不存在：同一 404 error 体
        MvcResult otherAccount = status(stranger.accessToken(), gimbalId);
        GimbalSession otherGimbal = gimbalSession();
        MvcResult otherGimbalResult = status(otherGimbal.accessToken(), gimbalId);
        MvcResult missing = status(stranger.accessToken(), UUID.randomUUID());
        assertEquals(404, otherAccount.getResponse().getStatus());
        assertIndistinguishableError(otherAccount, otherGimbalResult);
        assertIndistinguishableError(otherAccount, missing);
        assertEquals("RESOURCE_NOT_VISIBLE", errorOf(otherAccount).path("code").asText());
    }

    private static Set<String> fieldNames(JsonNode node) {
        Set<String> names = new HashSet<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }
}

package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * M2 设备端点集成测试基类：真实 PG @55435、MockMvc、共享临时库。
 *
 * <p>提供云台种子/设备会话、JSON 断言与"不可区分错误体"比较工具。所有测试
 * 自建数据（唯一 serial）以免共享库互相污染。</p>
 */
abstract class AbstractDeviceIT extends AbstractWebIT {

    @Autowired
    protected JdbcTemplate jdbc;

    @Autowired
    protected DeviceProperties deviceProps;

    protected record GimbalSession(UUID gimbalId, String credential, long credentialVersion,
                                   String accessToken) {
    }

    protected static String credentialOf(UUID gimbalId) {
        return "cred-" + gimbalId;
    }

    protected UUID seedGimbal(long credentialVersion) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                        + " VALUES (?, ?, ?, ?)",
                id, "gimbal-serial-" + id, credentialOf(id), credentialVersion);
        return id;
    }

    protected UUID seedGimbal() {
        return seedGimbal(1L);
    }

    protected String gimbalToken(UUID gimbalId, long credentialVersion) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + credentialOf(gimbalId)
                                + "\",\"credentialVersion\":\"" + credentialVersion
                                + "\",\"proof\":\"dev-proof\"}"))
                .andReturn();
        assertEquals(200, result.getResponse().getStatus(),
                result.getResponse().getContentAsString());
        return dataOf(result).path("sessionToken").asText();
    }

    protected GimbalSession gimbalSession() throws Exception {
        UUID id = seedGimbal(1L);
        return new GimbalSession(id, credentialOf(id), 1L, gimbalToken(id, 1L));
    }

    protected static JsonNode bodyOf(MvcResult result) throws Exception {
        return JSON.readTree(result.getResponse().getContentAsString());
    }

    protected static JsonNode dataOf(MvcResult result) throws Exception {
        return bodyOf(result).path("data");
    }

    protected static JsonNode errorOf(MvcResult result) throws Exception {
        return bodyOf(result).path("error");
    }

    protected static String writeJson(Object value) throws Exception {
        return JSON.writeValueAsString(value);
    }

    protected static String heartbeatJson(String epoch, String seq, String power, UUID taskId,
                                          UUID executionId, Object incidents) throws Exception {
        java.util.Map<String, Object> body = new java.util.LinkedHashMap<>();
        body.put("observationEpoch", epoch);
        body.put("observationSeq", seq);
        body.put("observedAt", java.time.Instant.now().toString());
        body.put("powerState", power);
        if (taskId != null) {
            body.put("taskId", taskId.toString());
        }
        if (executionId != null) {
            body.put("executionId", executionId.toString());
        }
        if (incidents != null) {
            body.put("incidents", incidents);
        }
        return writeJson(body);
    }

    protected long count(String table, String whereClause, Object... args) {
        Long value = jdbc.queryForObject("SELECT count(*) FROM " + table + " WHERE " + whereClause,
                Long.class, args);
        return value == null ? 0 : value;
    }

    /** 不可区分断言：HTTP 状态与 error 对象（不含每次尝试的 requestId）逐字一致。 */
    protected static void assertIndistinguishableError(MvcResult first, MvcResult second)
            throws Exception {
        assertEquals(first.getResponse().getStatus(), second.getResponse().getStatus());
        assertEquals(errorOf(first).toString(), errorOf(second).toString());
    }
}

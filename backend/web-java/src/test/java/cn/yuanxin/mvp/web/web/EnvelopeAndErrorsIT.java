package cn.yuanxin.mvp.web.web;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/** 信封形状与错误映射（契约 SuccessEnvelope/ErrorEnvelope；DD 3.1/3.2）。 */
class EnvelopeAndErrorsIT extends AbstractWebIT {

    private static final Pattern RFC3339 =
            Pattern.compile("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$");

    @Test
    @DisplayName("成功信封：{requestId,data,meta{replayed,serverTime}} + X-Request-Id 头一致")
    void successEnvelopeShape() throws Exception {
        MvcResult r = mockMvc.perform(post("/api/v1/auth/sms-challenges")
                        .contentType("application/json")
                        .content("{\"phone\":\"+8613900000001\",\"purpose\":\"login\"}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus());
        JsonNode body = JSON.readTree(r.getResponse().getContentAsString());
        String header = r.getResponse().getHeader("X-Request-Id");
        assertNotNull(header);
        UUID.fromString(header);
        assertEquals(header, body.path("requestId").asText());
        assertEquals(false, body.path("meta").path("replayed").asBoolean(true));
        assertTrue(RFC3339.matcher(body.path("meta").path("serverTime").asText()).matches());
        assertEquals(3, body.size(), "外层必须恰为 requestId/data/meta");
        assertFalse(body.path("data").path("challengeId").asText().isBlank());
        assertTrue(body.path("data").path("retryAfter").isInt());
    }

    @Test
    @DisplayName("Bean Validation → 400 INVALID_INPUT + details.fields")
    void validationMapsTo400() throws Exception {
        MvcResult r = mockMvc.perform(post("/api/v1/auth/sms-challenges")
                        .contentType("application/json")
                        .content("{\"phone\":\"not-a-phone\",\"purpose\":\"login\"}"))
                .andReturn();
        assertEquals(400, r.getResponse().getStatus());
        assertNotNull(r.getResponse().getHeader("X-Request-Id"));
        JsonNode body = JSON.readTree(r.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", body.path("error").path("code").asText());
        assertFalse(body.path("error").path("retryable").asBoolean(true));
        assertTrue(body.path("error").path("details").path("fields").isArray());
    }

    @Test
    @DisplayName("畸形 JSON → 400 INVALID_INPUT(malformed_json)")
    void malformedJsonIs400() throws Exception {
        MvcResult r = mockMvc.perform(post("/api/v1/auth/sms-challenges")
                        .contentType("application/json").content("{\"phone\": "))
                .andReturn();
        assertEquals(400, r.getResponse().getStatus());
        JsonNode body = JSON.readTree(r.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", body.path("error").path("code").asText());
        assertEquals("malformed_json", body.path("error").path("details").path("reason").asText());
    }

    @Test
    @DisplayName("重复 JSON 键 → 400（STRICT_DUPLICATE_DETECTION，不是覆盖）")
    void duplicateKeysRejected() throws Exception {
        MvcResult r = mockMvc.perform(post("/api/v1/auth/sms-challenges")
                        .contentType("application/json")
                        .content("{\"phone\":\"+8613900000002\",\"phone\":\"+8613900000003\","
                                + "\"purpose\":\"login\"}"))
                .andReturn();
        assertEquals(400, r.getResponse().getStatus());
        assertEquals("INVALID_INPUT",
                JSON.readTree(r.getResponse().getContentAsString())
                        .path("error").path("code").asText());
    }

    @Test
    @DisplayName("未知业务写字段 → 400（fail-on-unknown-properties）")
    void unknownFieldRejected() throws Exception {
        MvcResult r = mockMvc.perform(post("/api/v1/auth/sms-challenges")
                        .contentType("application/json")
                        .content("{\"phone\":\"+8613900000004\",\"purpose\":\"login\","
                                + "\"evil\":true}"))
                .andReturn();
        assertEquals(400, r.getResponse().getStatus());
        assertEquals("INVALID_INPUT",
                JSON.readTree(r.getResponse().getContentAsString())
                        .path("error").path("code").asText());
    }

    @Test
    @DisplayName("未映射路径 → 404 RESOURCE_NOT_VISIBLE（不泄露存在性）；"
            + "/api/** 未认证路径按次序先 401（业务路径拒绝先于占位）")
    void unmappedPathIsNotVisible() throws Exception {
        MvcResult r = mockMvc.perform(get("/nope-outside-api-space"))
                .andReturn();
        assertEquals(404, r.getResponse().getStatus());
        JsonNode body = JSON.readTree(r.getResponse().getContentAsString());
        assertEquals("RESOURCE_NOT_VISIBLE", body.path("error").path("code").asText());
        assertNotNull(r.getResponse().getHeader("X-Request-Id"));
    }

    @Test
    @DisplayName("非法游标 → 400 INVALID_INPUT(invalid_cursor)")
    void badCursorIs400() {
        CursorCodec codec = new CursorCodec(JSON);
        var ex = assertThrows(CursorException.class, () -> codec.decode("%%%not-base64%%%"));
        assertNotNull(ex.getMessage());
    }

    @Test
    @DisplayName("未映射异常 → 500 INTERNAL：只回 requestId，无堆栈")
    void unmappedExceptionIs500() throws Exception {
        MvcResult r = mockMvc.perform(get("/internal-test/boom")).andReturn();
        assertEquals(500, r.getResponse().getStatus());
        String raw = r.getResponse().getContentAsString();
        JsonNode body = JSON.readTree(raw);
        assertEquals("INTERNAL", body.path("error").path("code").asText());
        assertEquals(r.getResponse().getHeader("X-Request-Id"), body.path("requestId").asText());
        assertFalse(raw.contains("simulated unexpected failure"));
        assertFalse(raw.contains("IllegalStateException"));
        assertFalse(raw.contains("cn.yuanxin"));
    }

    @Test
    @DisplayName("204 无响应体但仍带 X-Request-Id 头")
    void noContentStillHasRequestId() throws Exception {
        LoginResult login = loginAppWithInstallation("+8613911112222", "inst-204test");
        MvcResult r = mockMvc.perform(delete("/api/v1/auth/sessions/current")
                        .header("Authorization", "Bearer " + login.accessToken()))
                .andReturn();
        assertEquals(204, r.getResponse().getStatus());
        assertEquals("", r.getResponse().getContentAsString());
        assertNotNull(r.getResponse().getHeader("X-Request-Id"));
        UUID.fromString(r.getResponse().getHeader("X-Request-Id"));
    }
}

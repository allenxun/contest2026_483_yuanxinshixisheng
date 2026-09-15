package cn.yuanxin.mvp.web.gimbalai;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalRevalidator;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.support.TestDatabase;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * 云台 AI 文本透传端点<b>预流</b>错误集成测试（MockMvc）：严格 body、GIMBAL-only、
 * 下游预流非 2xx。预流失败保持 JSON problem 映射（HTTP 状态）。
 *
 * <p>流式成功/流内失败见 {@link GimbalAiStreamingEndpointIT}（真实服务器 + SSE 增量断言）。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class GimbalAiEndpointIT {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String API_KEY = "TEST-API-KEY-PLACEHOLDER";
    private static final AiResponseStub STUB = new AiResponseStub();

    static {
        try {
            STUB.start();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", TestDatabase::url);
        registry.add("spring.datasource.username", TestDatabase::user);
        registry.add("spring.datasource.password", TestDatabase::password);
        registry.add("app.gimbal-ai.base-url", STUB::baseUrl);
        registry.add("app.gimbal-ai.api-key", () -> API_KEY);
        registry.add("app.gimbal-ai.connect-timeout-millis", () -> "2000");
        registry.add("app.gimbal-ai.read-timeout-millis", () -> "1000");
    }

    @TestConfiguration
    static class AuthConfig {
        @Bean
        @Primary
        PrincipalRevalidator alwaysValidRevalidator() {
            return new PrincipalRevalidator(null) {
                @Override
                public boolean stillValid(AuthenticatedPrincipal p) {
                    return true;
                }
            };
        }
    }

    @Autowired
    MockMvc mockMvc;

    @Autowired
    SessionProvider sessionProvider;

    @AfterEach
    void resetStub() {
        STUB.reset();
    }

    private String gimbalToken() {
        return sessionProvider.createGimbalSession(UUID.randomUUID(), 1L).sessionToken();
    }

    private String appToken() {
        return sessionProvider.createAppSession(UUID.randomUUID(), "inst-gimbal-ai", 1L).accessToken();
    }

    private MvcResult send(String token, String json) throws Exception {
        return mockMvc.perform(post("/api/v1/gimbal-ai/messages")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json")
                        .content(json))
                .andReturn();
    }

    private static JsonNode body(MvcResult result) throws Exception {
        return JSON.readTree(result.getResponse().getContentAsString());
    }

    @Test
    @DisplayName("预流严格 body：未知字段 / 空白 text / 超长 text → 400 INVALID_INPUT，且无下游调用")
    void strictBodyRejectsInvalidInput() throws Exception {
        String token = gimbalToken();

        MvcResult extra = send(token, "{\"text\":\"hi\",\"extra\":1}");
        assertThat(extra.getResponse().getStatus()).isEqualTo(400);
        assertThat(body(extra).path("error").path("code").asText()).isEqualTo("INVALID_INPUT");

        MvcResult blank = send(token, "{\"text\":\"   \"}");
        assertThat(blank.getResponse().getStatus()).isEqualTo(400);
        assertThat(body(blank).path("error").path("code").asText()).isEqualTo("INVALID_INPUT");

        MvcResult tooLong = send(token, "{\"text\":\"" + "x".repeat(2001) + "\"}");
        assertThat(tooLong.getResponse().getStatus()).isEqualTo(400);
        assertThat(body(tooLong).path("error").path("code").asText()).isEqualTo("INVALID_INPUT");

        assertThat(STUB.requests()).as("invalid input must not reach the downstream").isEmpty();
    }

    @Test
    @DisplayName("APP 主体 → 预流 403 CALLER_NOT_ALLOWED，且无任何下游调用")
    void appPrincipalForbidden() throws Exception {
        MvcResult result = send(appToken(), "{\"text\":\"hi\"}");
        assertThat(result.getResponse().getStatus()).isEqualTo(403);
        assertThat(body(result).path("error").path("code").asText()).isEqualTo("CALLER_NOT_ALLOWED");
        assertThat(STUB.requests()).isEmpty();
    }

    @Test
    @DisplayName("下游预流非 2xx → 503 DEPENDENCY_UNAVAILABLE（JSON problem，无 SSE）")
    void downstreamPreStreamNon2xxMapsToJson503() throws Exception {
        STUB.respond(503, "{\"code\":\"AI_SERVICE_UNAVAILABLE\",\"retryable\":true}");

        MvcResult result = send(gimbalToken(), "{\"text\":\"hi\"}");
        assertThat(result.getResponse().getStatus()).isEqualTo(503);
        assertThat(result.getResponse().getContentType()).contains("application/json");
        JsonNode envelope = body(result);
        assertThat(envelope.path("error").path("code").asText()).isEqualTo("DEPENDENCY_UNAVAILABLE");
        assertThat(envelope.path("data").isMissingNode()).isTrue();
        assertThat(STUB.requests()).hasSize(1);
    }
}

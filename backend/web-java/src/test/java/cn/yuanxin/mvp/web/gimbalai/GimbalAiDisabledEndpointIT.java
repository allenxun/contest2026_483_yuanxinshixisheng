package cn.yuanxin.mvp.web.gimbalai;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalRevalidator;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.support.TestDatabase;
import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
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
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * {@code app.providers.mode=disabled} 下端点的依赖不可用语义（HTTP 级）：
 * 云台请求 503 DEPENDENCY_UNAVAILABLE，绝不回退替身/合成答案。
 *
 * <p>认证用测试自有 {@link InMemorySessionDouble}（{@code @Primary} 覆盖 disabled 占位
 * 会话提供方）与恒真 revalidator，因此可在能力关闭下仍能到达业务路径。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = "app.providers.mode=disabled")
class GimbalAiDisabledEndpointIT {

    private static final ObjectMapper JSON = new ObjectMapper();

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", TestDatabase::url);
        registry.add("spring.datasource.username", TestDatabase::user);
        registry.add("spring.datasource.password", TestDatabase::password);
    }

    @TestConfiguration
    static class AuthConfig {
        @Bean
        @Primary
        SessionProvider testSessionProvider() {
            return new InMemorySessionDouble();
        }

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

    @Test
    @DisplayName("mode=disabled → 503 DEPENDENCY_UNAVAILABLE（无下游、无合成答案）")
    void disabledCapabilityReturns503() throws Exception {
        String token = sessionProvider.createGimbalSession(UUID.randomUUID(), 1L).sessionToken();

        MvcResult result = mockMvc.perform(post("/api/v1/gimbal-ai/messages")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json")
                        .content("{\"text\":\"hi\"}"))
                .andReturn();

        assertThat(result.getResponse().getStatus()).isEqualTo(503);
        JsonNode envelope = JSON.readTree(result.getResponse().getContentAsString());
        assertThat(envelope.path("error").path("code").asText()).isEqualTo("DEPENDENCY_UNAVAILABLE");
        assertThat(envelope.path("error").path("retryable").asBoolean()).isTrue();
        assertThat(envelope.path("data").path("answerText").isMissingNode()).isTrue();
    }
}

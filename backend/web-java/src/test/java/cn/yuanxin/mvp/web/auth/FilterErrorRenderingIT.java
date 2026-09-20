package cn.yuanxin.mvp.web.auth;

import cn.yuanxin.mvp.web.support.TestDatabase;
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
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/**
 * oracle round-2 R2-3：BearerAuthFilter 内的基础设施故障（provider/revalidator
 * 抛异常）必须收敛为标准 503 DEPENDENCY_UNAVAILABLE 信封 + X-Request-Id，
 * 不得裸抛逸出（过滤器在 MVC 异常处理之外）。用 @Primary 失败 revalidator 注入。
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class FilterErrorRenderingIT {

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", TestDatabase::url);
        registry.add("spring.datasource.username", TestDatabase::user);
        registry.add("spring.datasource.password", TestDatabase::password);
    }

    @TestConfiguration
    static class FailingRevalidatorConfig {
        @Bean
        @Primary
        PrincipalRevalidator failingRevalidator() {
            return new PrincipalRevalidator(null) {
                @Override
                public boolean stillValid(AuthenticatedPrincipal p) {
                    throw new IllegalStateException("simulated revalidate dependency failure");
                }
            };
        }
    }

    @Autowired
    MockMvc mockMvc;

    @Autowired
    SessionProvider sessionProvider;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    @DisplayName("revalidator 抛异常 → 503 DEPENDENCY_UNAVAILABLE 信封（retryable=true）+ X-Request-Id，无堆栈")
    void revalidatorInfrastructureFailureRenders503() throws Exception {
        // 替身直接签发合法会话（不经 SMS/DB），随后 revalidator 注入故障
        SessionProvider.IssuedAppSession issued =
                sessionProvider.createAppSession(UUID.randomUUID(), "inst-filter-err", 1L);

        MvcResult r = mockMvc.perform(get("/api/v1/system/echo-jobs/" + UUID.randomUUID())
                        .header("Authorization", "Bearer " + issued.accessToken()))
                .andReturn();

        assertEquals(503, r.getResponse().getStatus());
        String raw = r.getResponse().getContentAsString();
        assertFalse(raw.contains("IllegalStateException"));
        assertFalse(raw.contains("simulated revalidate dependency failure"));
        JsonNode body = objectMapper.readTree(raw);
        assertEquals("DEPENDENCY_UNAVAILABLE", body.path("error").path("code").asText());
        assertTrue(body.path("error").path("retryable").asBoolean());
        String header = r.getResponse().getHeader("X-Request-Id");
        assertNotNull(header);
        assertFalse(header.isBlank());
        assertEquals(header, body.path("requestId").asText());
    }
}

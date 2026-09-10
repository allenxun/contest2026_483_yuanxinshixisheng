package cn.yuanxin.mvp.web.auth;

import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import cn.yuanxin.mvp.web.web.RequestIdFilter;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * oracle round-2 R2-3（provider 分支）：SessionProvider.authenticate 抛异常 →
 * 503 DEPENDENCY_UNAVAILABLE 信封，不裸抛、不执行后续链（纯单元，无需 Spring）。
 */
class BearerAuthFilterTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    @DisplayName("provider.authenticate 抛异常 → 503 信封（retryable=true），链不继续")
    void providerFailureRenders503() throws Exception {
        SessionProvider throwing = new InMemorySessionDouble() {
            @Override
            public Optional<AuthenticatedPrincipal> authenticate(String accessToken) {
                throw new IllegalStateException("simulated auth provider outage");
            }
        };
        PrincipalRevalidator revalidator = new PrincipalRevalidator(null) {
            @Override
            public boolean stillValid(AuthenticatedPrincipal p) {
                return true;
            }
        };
        BearerAuthFilter filter = new BearerAuthFilter(throwing, revalidator, mapper);

        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/system/echo-jobs/x");
        request.addHeader("Authorization", "Bearer anything");
        request.setAttribute(RequestIdFilter.ATTR_REQUEST_ID, "rid-provider-fail");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, (rq, rs) -> {
            throw new AssertionError("filter chain must not continue after infrastructure failure");
        });

        assertEquals(503, response.getStatus());
        String raw = response.getContentAsString();
        assertTrue(!raw.contains("IllegalStateException") && !raw.contains("simulated auth provider outage"),
                raw);
        JsonNode body = mapper.readTree(raw);
        assertEquals("DEPENDENCY_UNAVAILABLE", body.path("error").path("code").asText());
        assertTrue(body.path("error").path("retryable").asBoolean());
        assertEquals("rid-provider-fail", body.path("requestId").asText());
    }
}

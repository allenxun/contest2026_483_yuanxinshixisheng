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
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * oracle round-2 R2-3（provider 分支）：SessionProvider.authenticate 抛异常 →
 * 503 DEPENDENCY_UNAVAILABLE 信封，不裸抛、不执行后续链（纯单元，无需 Spring）。
 */
class BearerAuthFilterTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    @DisplayName("context path 下的公开登录放行，业务接口仍校验并注入 Bearer 主体")
    void contextPathDoesNotBypassBearerAuthentication() throws Exception {
        InMemorySessionDouble sessions = new InMemorySessionDouble();
        PrincipalRevalidator revalidator = new PrincipalRevalidator(null) {
            @Override
            public boolean stillValid(AuthenticatedPrincipal p) {
                return true;
            }
        };
        BearerAuthFilter filter = new BearerAuthFilter(sessions, revalidator, mapper);

        MockHttpServletRequest login = contextRequest("POST", "/api/v1/gimbal-sessions");
        MockHttpServletResponse loginResponse = new MockHttpServletResponse();
        filter.doFilter(login, loginResponse, (request, response) ->
                loginResponse.setStatus(204));
        assertEquals(204, loginResponse.getStatus());

        String path = "/api/v1/gimbals/" + UUID.randomUUID() + "/current-assessment";
        MockHttpServletRequest missingBearer = contextRequest("GET", path);
        MockHttpServletResponse missingResponse = new MockHttpServletResponse();
        filter.doFilter(missingBearer, missingResponse, (request, response) -> {
            throw new AssertionError("protected route must not bypass authentication");
        });
        assertEquals(401, missingResponse.getStatus());
        assertEquals("AUTH_REQUIRED", mapper.readTree(missingResponse.getContentAsString())
                .path("error").path("code").asText());

        String token = sessions.createGimbalSession(UUID.randomUUID(), 1).sessionToken();
        MockHttpServletRequest authenticated = contextRequest("GET", path);
        authenticated.addHeader("Authorization", "Bearer " + token);
        MockHttpServletResponse authenticatedResponse = new MockHttpServletResponse();
        filter.doFilter(authenticated, authenticatedResponse, (request, response) -> {
            assertNotNull(request.getAttribute(BearerAuthFilter.ATTR_PRINCIPAL));
            authenticatedResponse.setStatus(204);
        });
        assertEquals(204, authenticatedResponse.getStatus());
    }

    private static MockHttpServletRequest contextRequest(String method, String applicationPath) {
        MockHttpServletRequest request = new MockHttpServletRequest(method, "/openvela" + applicationPath);
        request.setContextPath("/openvela");
        return request;
    }

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

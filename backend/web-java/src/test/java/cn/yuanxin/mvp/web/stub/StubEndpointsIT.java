package cn.yuanxin.mvp.web.stub;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;

/**
 * 501 契约占位（A/decisions #1）：抽样 M1–M5 共 7 个业务端点——
 * 已认证 → 501 + NOT_IMPLEMENTED 标准信封（绝不假 200）；未认证 → 401。
 */
class StubEndpointsIT extends AbstractWebIT {

    record StubCall(String label, java.util.function.Function<String,
            org.springframework.test.web.servlet.RequestBuilder> call) {
    }

    static Stream<Arguments> stubs() {
        UUID id = UUID.randomUUID();
        return Stream.of(
                Arguments.of("M1-A02 GET grants",
                        (java.util.function.Function<String, org.springframework.test.web.servlet.RequestBuilder>)
                                t -> get("/api/v1/me/member-access-grants")),
                Arguments.of("M1-A03 DELETE grant",
                        (java.util.function.Function<String, org.springframework.test.web.servlet.RequestBuilder>)
                                t -> delete("/api/v1/me/member-access-grants/" + id)),
                Arguments.of("M2-A02 heartbeat",
                        (java.util.function.Function<String, org.springframework.test.web.servlet.RequestBuilder>)
                                t -> post("/api/v1/gimbals/" + id + "/heartbeats")
                                        .contentType("application/json").content("{}")),
                Arguments.of("M4-A05 observations",
                        (java.util.function.Function<String, org.springframework.test.web.servlet.RequestBuilder>)
                                t -> post("/api/v1/care-executions/" + id + "/observations")
                                        .contentType("application/json").content("{}")),
                Arguments.of("M2-A06 PUT binding",
                        (java.util.function.Function<String, org.springframework.test.web.servlet.RequestBuilder>)
                                t -> org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                                        .put("/api/v1/me/gimbal-bindings/" + id)),
                Arguments.of("M5-A01 PUT destination",
                        (java.util.function.Function<String, org.springframework.test.web.servlet.RequestBuilder>)
                                t -> org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                                        .put("/api/v1/me/notification-destinations/inst-1")));
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("stubs")
    @DisplayName("已认证业务 stub → 501 NOT_IMPLEMENTED 标准信封")
    void authenticatedStubIs501(String label,
                                java.util.function.Function<String,
                                        org.springframework.test.web.servlet.RequestBuilder> call)
            throws Exception {
        String token = loginApp(newPhone());
        MvcResult r = mockMvc.perform(((org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder)
                        call.apply(token))
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", "stub-" + UUID.randomUUID()))
                .andReturn();
        assertEquals(501, r.getResponse().getStatus(), label);
        JsonNode err = JSON.readTree(r.getResponse().getContentAsString()).path("error");
        assertEquals("NOT_IMPLEMENTED", err.path("code").asText(), label);
        assertFalse(err.path("retryable").asBoolean(true));
        assertTrue(err.path("details").path("apiId").isTextual(), label);
        assertNotNull(r.getResponse().getHeader("X-Request-Id"));
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("stubs")
    @DisplayName("未认证业务 stub 路径 → 401（先拒绝认证再谈实现）")
    void unauthenticatedStubIs401(String label,
                                  java.util.function.Function<String,
                                          org.springframework.test.web.servlet.RequestBuilder> call)
            throws Exception {
        MvcResult r = mockMvc.perform(call.apply("")).andReturn();
        assertEquals(401, r.getResponse().getStatus(), label);
        assertEquals("AUTH_REQUIRED",
                JSON.readTree(r.getResponse().getContentAsString())
                        .path("error").path("code").asText());
    }

    @Test
    @DisplayName("stub 路径参数 UUID 非法 → 400 INVALID_INPUT（已认证）")
    void badUuidPathParameter() throws Exception {
        String token = loginApp(newPhone());
        MvcResult r = mockMvc.perform(get("/api/v1/skin-reports/not-uuid")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(400, r.getResponse().getStatus());
        assertEquals("INVALID_INPUT",
                JSON.readTree(r.getResponse().getContentAsString())
                        .path("error").path("code").asText());
    }
}

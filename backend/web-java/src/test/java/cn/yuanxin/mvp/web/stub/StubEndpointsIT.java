package cn.yuanxin.mvp.web.stub;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.util.ClassUtils;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import org.springframework.web.util.pattern.PathPattern;

import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/**
 * 契约占位（501 NOT_IMPLEMENTED）归零后的**路由表回归守卫**。
 *
 * <p>历史：A 交付时 {@link NotYetImplementedController} 以 26 个 501 占位守住所有
 * contract-only 端点（"未实现端点绝不假 200"）；B 实现 M1/M2/M5 后删除自己的 11 个，
 * C/D 实现 M3/M4 后删除其余 15 个。合并集成基线后该控制器**已无任何请求映射**，
 * 因此原先"抽样调用 → 断言 501"的参数化测试失去对象，按总协调裁定删除。</p>
 *
 * <p>本类改用 Spring 实际的 {@link RequestMappingHandlerMapping} 做正面证明，因为：
 * <ul>
 *   <li>非 501 抽样**不能**作为唯一证明——端点可能根本未注册（404）或注册到了错误的
 *       method/path，而 404/400 同样无法证明路由正确；</li>
 *   <li>路由表能同时证明两件事：占位控制器不再拥有任何业务映射；原清单中的每个端点
 *       都由**真实业务 controller** 以正确的 HTTP method + path 模板注册。</li>
 * </ul>
 * 参数化清单为 B/C/D 三方合并前曾属 contract-only 的端点并集，**非空**——不用空参数
 * 列表制造假通过。各端点的业务语义（权限、幂等、错误码、落库）仍由 B/C/D 各自的业务
 * 测试覆盖，本类只守路由这一层。</p>
 */
class StubEndpointsIT extends AbstractWebIT {

    @Autowired
    private ApplicationContext ctx;

    private RequestMappingHandlerMapping mapping() {
        return ctx.getBean("requestMappingHandlerMapping", RequestMappingHandlerMapping.class);
    }

    /**
     * 曾属 contract-only 的端点并集（HTTP method + 完整 path 模板）。
     * B 的 11 个（M1-A01～A03、M2-A02～A08、M5-A01；M2-A01 自始由 foundation-auth
     * 实现，不在占位清单内）+ 原抽样清单中的 C/D 端点 6 个。
     */
    static Stream<Arguments> formerContractOnlyEndpoints() {
        return Stream.of(
                // ---- B 包（identity / devices / notifications）----
                Arguments.of("POST", "/api/v1/member-access-grants"),
                Arguments.of("GET", "/api/v1/me/member-access-grants"),
                Arguments.of("DELETE", "/api/v1/me/member-access-grants/{grantId}"),
                Arguments.of("POST", "/api/v1/gimbals/{gimbalId}/heartbeats"),
                Arguments.of("GET", "/api/v1/gimbals/{gimbalId}/status"),
                Arguments.of("POST", "/api/v1/microcrystal-observations"),
                Arguments.of("GET", "/api/v1/microcrystals/{microcrystalId}/capabilities"),
                Arguments.of("PUT", "/api/v1/me/gimbal-bindings/{gimbalId}"),
                Arguments.of("GET", "/api/v1/gimbals/{gimbalId}/binding-status"),
                Arguments.of("DELETE", "/api/v1/me/gimbal-bindings/{gimbalId}"),
                Arguments.of("PUT", "/api/v1/me/notification-destinations/{installationId}"),
                // ---- C/D 包（原 501 抽样清单中的端点）----
                Arguments.of("POST", "/api/v1/skin-assessment-tasks"),
                Arguments.of("GET", "/api/v1/skin-assessment-tasks/{taskId}"),
                Arguments.of("GET", "/api/v1/gimbals/{gimbalId}/current-assessment"),
                Arguments.of("POST", "/api/v1/care-executions"),
                Arguments.of("POST", "/api/v1/care-executions/{executionId}/observations"),
                Arguments.of("GET", "/api/v1/care-plans/{planId}/progress"));
    }

    @Test
    @DisplayName("占位控制器不再拥有任何业务请求映射（501 占位已归零）")
    void placeholderControllerOwnsNoBusinessMappings() {
        Set<String> remaining = new LinkedHashSet<>();
        for (Map.Entry<RequestMappingInfo, HandlerMethod> e : mapping().getHandlerMethods().entrySet()) {
            Class<?> beanType = ClassUtils.getUserClass(e.getValue().getBeanType());
            if (NotYetImplementedController.class.isAssignableFrom(beanType)) {
                remaining.add(e.getValue().getMethod().getName() + " -> " + patterns(e.getKey()));
            }
        }
        assertTrue(remaining.isEmpty(),
                "NotYetImplementedController 仍持有业务映射（占位未归零）：" + remaining);
    }

    @ParameterizedTest(name = "{0} {1}")
    @MethodSource("formerContractOnlyEndpoints")
    @DisplayName("原 contract-only 端点均由真实业务 controller 注册 method+path")
    void formerContractOnlyEndpointIsServedByRealController(String method, String path) {
        Map<String, Set<String>> table = routeTable();
        String key = method + " " + normalize(path);
        Set<String> owners = table.get(key);
        assertNotNull(owners,
                "路由表中不存在 " + key + "（端点未注册或 method/path 不符）；实际路由表=" + table.keySet());
        assertFalse(owners.contains(NotYetImplementedController.class.getSimpleName()),
                key + " 仍由占位控制器提供，而非真实业务 controller");
        assertFalse(owners.isEmpty(), key + " 无任何归属 controller");
    }

    @Test
    @DisplayName("真实路由的非法 UUID 路径参数 → 400 INVALID_INPUT（已认证）")
    void badUuidPathParameter() throws Exception {
        String token = loginApp(newPhone());
        MvcResult r = mockMvc.perform(get("/api/v1/skin-reports/not-uuid")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(400, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode err = JSON.readTree(r.getResponse().getContentAsString()).path("error");
        assertEquals("INVALID_INPUT", err.path("code").asText());
    }

    // ---------------- helpers ----------------

    /** "METHOD 归一化path" -> 归属 controller 简单类名集合。 */
    private Map<String, Set<String>> routeTable() {
        Map<String, Set<String>> table = new TreeMap<>();
        for (Map.Entry<RequestMappingInfo, HandlerMethod> e : mapping().getHandlerMethods().entrySet()) {
            RequestMappingInfo info = e.getKey();
            String owner = ClassUtils.getUserClass(e.getValue().getBeanType()).getSimpleName();
            Set<String> methods = info.getMethodsCondition().getMethods().isEmpty()
                    ? Set.of("GET", "POST", "PUT", "DELETE", "PATCH")
                    : info.getMethodsCondition().getMethods().stream()
                            .map(Enum::name).collect(Collectors.toCollection(LinkedHashSet::new));
            for (String pattern : patterns(info)) {
                String normalized = normalize(pattern);
                for (String m : methods) {
                    table.computeIfAbsent(m + " " + normalized, k -> new LinkedHashSet<>()).add(owner);
                }
            }
        }
        return table;
    }

    /**
     * 合并后的 path 模板（class 级 {@code @RequestMapping} 前缀 + 方法级路径）。
     *
     * <p>Spring Framework 6（本项目 Boot 3）已移除 {@code RequestMappingInfo
     * .getPatternCondition()}（AntPathMatcher 分支），统一使用 PathPatternParser，
     * 故只读 {@code getPathPatternsCondition()}；为 null（无路径条件的映射）时返回空集。</p>
     */
    private static Set<String> patterns(RequestMappingInfo info) {
        Set<String> out = new LinkedHashSet<>();
        if (info.getPathPatternsCondition() != null) {
            for (PathPattern p : info.getPathPatternsCondition().getPatterns()) {
                out.add(p.getPatternString());
            }
        }
        return out;
    }

    /** 路径变量名由各 controller 自定（grantId/taskId/…），归一化为 {} 后比较。 */
    private static String normalize(String path) {
        return path.replaceAll("\\{[^/]*}", "{}");
    }
}

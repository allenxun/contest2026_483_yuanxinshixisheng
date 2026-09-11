package cn.yuanxin.mvp.web.docs;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;
import org.yaml.snakeyaml.Yaml;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/**
 * 文档启用（test profile）时的 B 包 springdoc 文档验证。
 *
 * <p>期望集合<strong>不在测试里硬编码</strong>，而是用 snakeyaml 读取权威契约
 * {@code ../contracts/openapi/openapi.yaml} 的 {@code x-api-id} 操作——单一事实来源，
 * 契约变更时测试自动跟随/失败，避免 27 条清单手抄漂移。Maven Surefire 的工作目录
 * 为模块 basedir（backend/web-java），故相对路径稳定。</p>
 *
 * <p>本类继承 {@link AbstractWebIT}（同一 test profile + 同一 mock 上下文），
 * <b>不新增 Spring 上下文</b>。</p>
 */
class OpenApiDocsIT extends AbstractWebIT {

    private static final List<String> METHODS = List.of("get", "post", "put", "delete", "patch");

    @Test
    @DisplayName("dev/test：/v3/api-docs 由实际 Controller 生成且 27 个业务路由全部可见")
    void apiDocsContainsAll27ContractBusinessRoutes() throws Exception {
        MvcResult r = mockMvc.perform(get("/v3/api-docs")).andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode doc = JSON.readTree(r.getResponse().getContentAsString());

        assertTrue(doc.hasNonNull("openapi"), "generated doc must declare openapi version");
        assertTrue(doc.has("paths"), "generated doc must contain generated paths");

        Set<String> actual = extractOperations(doc);
        Set<String> expected = expectedFromContract();
        assertEquals(27, expected.size(), "contract x-api-id operation count changed: " + expected);

        Set<String> missing = new LinkedHashSet<>(expected);
        missing.removeAll(actual);
        assertTrue(missing.isEmpty(), "27 业务 API 未在生成文档出现（missing=" + missing
                + "）；实际路由=" + actual);
        assertTrue(actual.containsAll(expected), "expected routes must all be visible");
    }

    @Test
    @DisplayName("dev/test：bearerAuth 安全方案、全局 security 与 4 个公开端点覆盖正确")
    void securitySemanticsMatchContract() throws Exception {
        MvcResult r = mockMvc.perform(get("/v3/api-docs")).andReturn();
        JsonNode doc = JSON.readTree(r.getResponse().getContentAsString());

        JsonNode scheme = doc.path("components").path("securitySchemes").path("bearerAuth");
        assertEquals("http", scheme.path("type").asText());
        assertEquals("bearer", scheme.path("scheme").asText());
        assertEquals(1, doc.path("security").size(), "global security should default to bearerAuth");

        Map<String, String> publicOps = Map.of(
                "/api/v1/auth/sms-challenges", "post",
                "/api/v1/auth/sessions", "post",
                "/api/v1/auth/session-refreshes", "post",
                "/api/v1/gimbal-sessions", "post");
        for (Map.Entry<String, String> e : publicOps.entrySet()) {
            JsonNode op = doc.path("paths").path(e.getKey()).path(e.getValue());
            assertNotNull(op, "public op missing: " + e);
            assertTrue(op.path("security").isArray() && op.path("security").size() == 0,
                    "public op must override global security with []: " + e);
        }
    }

    @Test
    @DisplayName("dev/test：Swagger UI 页面可加载（index.html 与根路径 forward 均 200）")
    void swaggerUiLoads() throws Exception {
        MvcResult index = mockMvc.perform(get("/swagger-ui/index.html")).andReturn();
        assertEquals(200, index.getResponse().getStatus());
        assertTrue(index.getResponse().getContentAsString().toLowerCase(Locale.ROOT).contains("swagger"));

        MvcResult root = mockMvc.perform(get("/swagger-ui/")).andReturn();
        assertEquals(200, root.getResponse().getStatus(),
                "/swagger-ui/ should forward to the UI index");
    }

    // ---------------- helpers ----------------

    /** 生成文档的实际 (method lower, normalized path) 集合。 */
    private static Set<String> extractOperations(JsonNode doc) {
        Set<String> out = new LinkedHashSet<>();
        JsonNode paths = doc.path("paths");
        paths.fieldNames().forEachRemaining(p -> {
            JsonNode item = paths.get(p);
            for (String m : METHODS) {
                if (item.has(m)) {
                    out.add(m + " " + normalize(p));
                }
            }
        });
        return out;
    }

    /** 权威契约中带 x-api-id 的操作集合。 */
    @SuppressWarnings("unchecked")
    private static Set<String> expectedFromContract() throws Exception {
        Path yamlPath = Path.of("..", "contracts", "openapi", "openapi.yaml");
        assertTrue(Files.exists(yamlPath), "contract not found at " + yamlPath.toAbsolutePath());
        Map<String, Object> contract;
        try (InputStream in = Files.newInputStream(yamlPath)) {
            contract = new Yaml().load(in);
        }
        Map<String, Object> paths = (Map<String, Object>) contract.get("paths");
        assertNotNull(paths, "contract has no paths section");
        Set<String> out = new LinkedHashSet<>();
        for (Map.Entry<String, Object> e : paths.entrySet()) {
            Map<String, Object> item = (Map<String, Object>) e.getValue();
            for (String m : METHODS) {
                Object op = item.get(m);
                if (op instanceof Map<?, ?> opMap && opMap.containsKey("x-api-id")) {
                    out.add(m + " " + normalize(e.getKey()));
                }
            }
        }
        return out;
    }

    /** 路径变量名由各 controller 自定，统一归一化为 {}。 */
    private static String normalize(String path) {
        return path.replaceAll("\\{[^/]*\\}", "{}");
    }
}

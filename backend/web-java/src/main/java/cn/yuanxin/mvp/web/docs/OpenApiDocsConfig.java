package cn.yuanxin.mvp.web.docs;

import cn.yuanxin.mvp.web.docs.catalog.ApiDocsCatalog;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 从<strong>实际 Controller/DTO</strong>（springdoc 扫描 {@code @RestController}
 * 与 handler 方法签名）生成 OpenAPI 的 B 包文档配置。
 *
 * <p><b>仅 dev/test profile 且 springdoc 明确启用时注册</b>（{@link Profile} +
 * {@link ConditionalOnProperty}）：生产不注册任何文档 bean；{@link DocsProductionGuard}
 * 则始终注册，按运行时生产信号（active profile 含 prod 或 app.env=production）对任何
 * 误启用做 fail-closed，不因 profile/env 被覆盖而失效。</p>
 *
 * <p>契约权威仍是 {@code backend/contracts/openapi/openapi.yaml}：本配置只补充
 * <em>语义说明</em>（info、bearerAuth、公开端点清单），不复制/改写业务字段级
 * 契约，也不改变任何运行时行为。生成的 {@code paths} 来自 Spring MVC 的真实
 * 路由表，不是旧手写 YAML 的回显。</p>
 */
@Configuration(proxyBeanMethods = false)
@Profile({"dev", "test"})
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class OpenApiDocsConfig {

    /**
     * 契约中 {@code security: []} 的公开（无 Bearer）端点清单
     * （contracts/openapi/openapi.yaml 各 operation 的 security 覆盖）：
     * 手机号挑战/登录/刷新 + 云台设备会话握手。全局默认 bearerAuth。
     */
    private static final Map<String, Set<String>> PUBLIC_OPERATIONS = Map.of(
            "/api/v1/auth/sms-challenges", Set.of("post"),
            "/api/v1/auth/sessions", Set.of("post"),
            "/api/v1/auth/session-refreshes", Set.of("post"),
            "/api/v1/gimbal-sessions", Set.of("post"));

    @Bean
    public OpenAPI mvpOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("AI 皮肤护理系统 后端 MVP（由实际 Controller/DTO 生成）")
                        .version("0.1.0")
                                .description("""
                                本页由运行中的 Java 后端（Spring MVC + springdoc 2.8.x）从实际 Controller/DTO
                                生成，非手写 YAML 回显。它**不是**权威契约：字段级/错误码级契约的权威来源是
                                backend/contracts/openapi/openapi.yaml；两者不一致时以契约文件为准。
                                生成文档为 OpenAPI 3.1.0，权威契约为 OpenAPI 3.0.3；operationId 由 Java 方法名
                                派生，未对齐契约 operationId。

                                == 联调导读 ==

                                【统一响应信封】
                                - 成功：{requestId, data, meta:{replayed, serverTime}}；每个成功响应的 data 均为该端点的
                                  真实类型（见各响应 schema，不再是不可展开的 object）。
                                - 204：无响应体（requestId 见 X-Request-Id 头）。
                                - 错误：{requestId, error:{code, message, retryable, details?}}；由
                                  GlobalExceptionHandler 统一渲染，控制器不自拼错误体。
                                - 列表：data = {items:[], nextCursor:string|null}；分页 limit 默认 20、上限 100；
                                  cursor 为不透明游标（原样回传；非法游标 400 INVALID_INPUT，details.reason=invalid_cursor）。
                                - 每个响应（含错误与 204）都带 X-Request-Id 头；每个 HTTP 尝试生成新的 requestId，
                                  与 T13 稳定逻辑请求 ID 区分，不能用作幂等键。

                                【类型与格式】
                                - JSON 字段 camelCase；DB/任务内 payload 为 snake_case。
                                - bigint（N/K/revision/seq/计数/版本）在 JSON 中一律为十进制字符串（pattern ^(0|[1-9][0-9]*)$）。
                                - schema_version 为 JSON 整数（如 1）。
                                - 时间为 RFC3339 UTC、秒精度（如 2026-09-13T08:30:00Z）。

                                【鉴权】全局默认 BearerAuth；下列 4 个公开端点无 Bearer（契约 security: []）：
                                POST /api/v1/auth/sms-challenges、POST /api/v1/auth/sessions、
                                POST /api/v1/auth/session-refreshes、POST /api/v1/gimbal-sessions。
                                其余端点要求 Authorization: Bearer <APP session token | gimbal device session token>。
                                主体身份只由服务端从 token 派生，请求体不能声明 accountId/gimbalId。
                                本页全局 bearer 只表达“是否需要 token”，不表达 APP/GIMBAL 类型限制与
                                成员查看授权/当前任务/绑定关系等细粒度权限（由后端运行时强制，以契约各端点描述为准）。

                                【幂等（Idempotency-Key）】
                                - 除 M2-A01 握手与 M2-A02 心跳（按 epoch/seq 去重）外，业务写接口要求
                                  Idempotency-Key（1-128 字符）。
                                - 同键同内容：重放原结果，meta.replayed=true（不重做写入）。
                                - 同键不同内容：409 IDEMPOTENCY_CONTENT_CONFLICT；这是新的逻辑请求，必须换新键。
                                - 处理中：409 REQUEST_IN_PROGRESS（retryable），按 Retry-After 等待后以同一逻辑键重试。
                                - T13 主键为 (principal_type, principal_id, operation, idempotency_key)；**无 TTL**，
                                  不得按短 TTL 清理。返回体各错误码的客户端动作见对应错误响应 description。

                                【multipart 约定】metadata part 为 application/json（严格解析），图片 part 为二进制
                                （image/jpeg、image/png 等，单图上限开发初值 10MiB，以内容嗅探为准）；响应
                                Cache-Control: no-store。

                                【主要调用链与顺序】
                                1) 测肤链：POST /api/v1/gimbal-sessions（云台握手）→ POST /api/v1/skin-assessment-tasks
                                   （M3-A01，202 受理）→ worker 分析 → GET /api/v1/skin-assessment-tasks/{taskId} 轮询
                                   status；需补拍时 PUT …/photo-versions/{photoVersion}（M3-A02，202；须 needs_retake 且
                                   版本=当前版本+1）。
                                2) 护理链：GET /api/v1/members/{memberId}/skin-reports → GET /api/v1/skin-reports/{reportId}
                                   → GET /api/v1/members/{memberId}/care-plans → GET /api/v1/care-plans/{planId}（就绪后）
                                   → POST /api/v1/care-executions（开始执行，multipart）→ POST …/observations 同步测量
                                   → POST …/closure-confirmations 收尾 → GET /api/v1/care-executions/{executionId}
                                   读进度/记录。
                                3) 配网绑定通知链：POST /api/v1/gimbal-sessions → PUT /api/v1/me/gimbal-bindings/{gimbalId}
                                   （绑定）→ GET /api/v1/gimbals/{gimbalId}/binding-status（轮询绑定结果）→
                                   PUT /api/v1/me/notification-destinations/{installationId}（登记推送目标）→
                                   DELETE /api/v1/me/gimbal-bindings/{gimbalId} 解绑（204）。

                                【自由结构】Java 侧声明为 Object/Map/JsonNode 的字段若无法静态展开为字段级 schema，
                                会在该字段 description 中给出已知键、schema_version 口径与**可扩展边界**（哪些键封闭、
                                哪些开放扩展）；客户端必须容忍开放扩展键；服务端内部诊断键（failure_detail/last_error
                                原始内容等）绝不外发。

                                【部署限制】本页仅在 dev/test 启用；生产（app.env=production 或 prod profile）文档端点
                                关闭，强制启用将拒绝启动。Swagger UI 不得用于公网生产。
                                """));
    }

    /**
     * 契约级安全语义修正（只作用于生成后的文档对象）：
     * <ol>
     *   <li>全局默认 {@code bearerAuth}（与契约顶层 security 一致）；</li>
     *   <li>4 个公开端点显式置空 security（契约中这些 operation 为 {@code security: []}）；</li>
     *   <li>移除 springdoc 对认证主体参数（{@code PrincipalContext principal}）可能
     *       生成的伪请求参数——它由 BearerAuthFilter 从 token 注入，非客户端输入。</li>
     * </ol>
     */
    @Bean
    public OpenApiCustomizer contractSecurityCustomizer() {
        return new OrderedOpenApiCustomizer(Ordered.HIGHEST_PRECEDENCE, openApi -> {
            // springdoc 会用自身生成的 components 覆盖 OpenAPI bean 上的 components，
            // 故安全方案/全局 security 必须在生成后的 customizer 里设置。
            Components components = openApi.getComponents() == null
                    ? new Components() : openApi.getComponents();
            components.addSecuritySchemes("bearerAuth", new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .description("APP session token（POST /api/v1/auth/sessions 签发）或"
                            + " gimbal device session token（POST /api/v1/gimbal-sessions 签发）。"
                            + "主体身份只由 token 决定，请求体不能声明 accountId/gimbalId。"));
            openApi.setComponents(components);
            openApi.setSecurity(new ArrayList<>(
                    List.of(new SecurityRequirement().addList("bearerAuth"))));
            if (openApi.getPaths() == null) {
                return;
            }
            openApi.getPaths().forEach((path, item) -> {
                for (Map.Entry<PathItem.HttpMethod, Operation> entry : item.readOperationsMap().entrySet()) {
                    Operation operation = entry.getValue();
                    if (isPublic(path, entry.getKey())) {
                        operation.setSecurity(new ArrayList<>());
                    }
                    removeAuthenticatedPrincipalParameter(operation);
                }
            });
        });
    }

    /**
     * 集中式联调文档施加引擎：在各目录道提供 {@link ApiDocsCatalog} bean 后生效。
     * 未提供任何目录时为空操作，{@code /v3/api-docs} 仍 200（覆盖率缺口由门禁测试断言，
     * 不在运行期抛错）；结构性错误（重复/漂移键、参数不符）则 fail fast。
     */
    @Bean
    public ApiDocsApplier apiDocsApplier(List<ApiDocsCatalog> catalogs, ObjectMapper objectMapper) {
        return new ApiDocsApplier(catalogs, objectMapper);
    }

    /** 可排序的 {@link OpenApiCustomizer} 包装，用于保证施加顺序确定。 */
    private static final class OrderedOpenApiCustomizer implements OpenApiCustomizer, Ordered {
        private final int order;
        private final OpenApiCustomizer delegate;

        private OrderedOpenApiCustomizer(int order, OpenApiCustomizer delegate) {
            this.order = order;
            this.delegate = delegate;
        }

        @Override
        public int getOrder() {
            return order;
        }

        @Override
        public void customise(OpenAPI openApi) {
            delegate.customise(openApi);
        }
    }

    /**
     * springdoc 只映射 {@code /swagger-ui/index.html}，目录请求 {@code /swagger-ui/}
     * 默认 404。仅在文档启用时补一个内部 forward，使 UI 根地址也可直接打开
     * （转发非业务 200，不涉及任何业务端点）。
     */
    @Bean
    public WebMvcConfigurer swaggerUiRootForward() {
        return new WebMvcConfigurer() {
            @Override
            public void addViewControllers(ViewControllerRegistry registry) {
                registry.addViewController("/swagger-ui/")
                        .setViewName("forward:/swagger-ui/index.html");
            }
        };
    }

    private static boolean isPublic(String path, PathItem.HttpMethod method) {
        Set<String> methods = PUBLIC_OPERATIONS.get(path);
        return methods != null && methods.contains(method.name().toLowerCase(java.util.Locale.ROOT));
    }

    /** 删除由 Spring 参数解析器注入的 principal 伪参数（name=principal），不改其他参数。 */
    private static void removeAuthenticatedPrincipalParameter(Operation operation) {
        if (operation.getParameters() == null) {
            return;
        }
        List<io.swagger.v3.oas.models.parameters.Parameter> kept = new ArrayList<>();
        for (io.swagger.v3.oas.models.parameters.Parameter p : operation.getParameters()) {
            if (!"principal".equals(p.getName())) {
                kept.add(p);
            }
        }
        operation.setParameters(kept.isEmpty() ? null : kept);
    }
}

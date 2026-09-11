package cn.yuanxin.mvp.web.docs;

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
 * {@link ConditionalOnProperty}）：生产 profile 不注册任何文档 bean，
 * {@link DocsProductionGuard} 再对 app.env=production 下的误启用做 fail-closed。</p>
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
                                生成，非手写 YAML 回显。字段级/错误码级契约的权威来源仍是
                                backend/contracts/openapi/openapi.yaml；两者不一致时以契约文件为准。

                                统一响应信封：
                                - 成功：{requestId, data, meta:{replayed, serverTime}}；204 无响应体。
                                - 列表：data = {items:[], nextCursor: string|null}；limit 默认 20、上限 100。
                                - 错误：{requestId, error:{code, message, retryable, details}}；
                                  错误经 GlobalExceptionHandler 统一渲染，控制器不自拼错误体。
                                - 每个响应（含错误与 204）带 X-Request-Id 头；每次 HTTP 尝试生成
                                  新的 requestId，与 T13 稳定逻辑请求 ID 区分。

                                鉴权：全局默认 BearerAuth；下列 4 个公开端点无 Bearer（契约中为 security: []）：
                                POST /api/v1/auth/sms-challenges、POST /api/v1/auth/sessions、
                                POST /api/v1/auth/session-refreshes、POST /api/v1/gimbal-sessions。
                                其余端点要求 Authorization: Bearer <APP session token | gimbal device session token>。
                                主体身份只由服务端从会话派生，请求体不能声明 accountId/gimbalId。
                                BearerAuthFilter 仅保护 /api/**；本文档端点（/v3/api-docs、
                                /swagger-ui/**）不在 /api/** 下，故无需为文档放行鉴权。

                                其他公共规则：JSON 字段 camelCase、DB/任务 payload snake_case；
                                bigint（N/K/revision/seq/计数）在 JSON 中为十进制字符串
                                （pattern ^(0|[1-9][0-9]*)$）；时间为 RFC3339 UTC。
                                业务写接口（除 M2-A01 握手与 M2-A02 心跳按 epoch/seq 去重外）要求
                                Idempotency-Key（1-128 字符），相同键相同内容重放原结果
                                （meta.replayed=true），相同键不同内容 409 IDEMPOTENCY_CONTENT_CONFLICT。

                                尚未字段级展开（本页只显示为自由结构 object；字段级权威见契约文件）：
                                - B devices/DeviceDtos.CapabilitiesView.capabilities（JSONB 自由结构）
                                - C care/CareProjections.planSummary 与 .plan（JSONB 自由结构）
                                - D assessments/dto/SkinReportListItem.reportSummary 与
                                  SkinReportView.metrics（JSONB 自由结构）
                                另有 M1-A01 的 multipart metadata 部件为严格 JSON（capture +
                                consentEvidenceRef），字段级 schema 同样见契约，不在本页展开。
                                因此本页“由实际 Controller/DTO 生成”指的是路由与可静态推导的
                                请求/响应形状，不宣称所有自由结构成员都已具备字段级 schema。

                                本页面仅在 dev/test 启用；app.env=production 下文档端点关闭，强制启用将拒绝启动。
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
        return openApi -> {
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
        };
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

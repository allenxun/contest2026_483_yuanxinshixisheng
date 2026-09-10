package cn.yuanxin.mvp.web.auth;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.ErrorEnvelope;
import cn.yuanxin.mvp.web.web.RequestIdFilter;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Optional;
import java.util.Set;

/**
 * Bearer 认证过滤器：保护 /api/**，除公开清单（无 Bearer 的基础认证端点）。
 * actuator 不在 /api/** 下 → 开放。
 *
 * <p>身份只从 token 派生：请求体里的 accountId/installationId/gimbalId 字段
 * 一律不作为认证依据（fail closed；digest §6）。缺失 Authorization →
 * 401 AUTH_REQUIRED；token 非本提供方签发/已撤销/过期 → 401 SESSION_INVALID。</p>
 *
 * <p>501 业务 stub 在本过滤器之后执行：未认证请求先拿到 401（证明业务路径
 * 的无效认证拒绝），已认证请求拿到 501 NOT_IMPLEMENTED。</p>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class BearerAuthFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(BearerAuthFilter.class);

    public static final String ATTR_PRINCIPAL = "mvp.principal";

    /** 公开（无 Bearer）端点：method + 精确 path。 */
    private static final Set<String> PUBLIC = Set.of(
            "POST /api/v1/auth/sms-challenges",
            "POST /api/v1/auth/sessions",
            "POST /api/v1/auth/session-refreshes",
            "POST /api/v1/gimbal-sessions");

    private final SessionProvider sessionProvider;
    private final PrincipalRevalidator revalidator;
    private final ObjectMapper objectMapper;

    public BearerAuthFilter(SessionProvider sessionProvider, PrincipalRevalidator revalidator,
                            ObjectMapper objectMapper) {
        this.sessionProvider = sessionProvider;
        this.revalidator = revalidator;
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String path = request.getRequestURI();
        if (!path.startsWith("/api/") || PUBLIC.contains(request.getMethod() + " " + path)) {
            chain.doFilter(request, response);
            return;
        }
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ") || header.substring(7).isBlank()) {
            reject(response, ErrorCode.AUTH_REQUIRED, "missing bearer token");
            return;
        }
        String token = header.substring(7);
        // 认证/复核在 MVC 异常处理之外的过滤器内执行：任何基础设施异常都必须
        // 在此收敛为标准错误信封（oracle round-2 R2-3），不得裸抛逸出。
        Optional<AuthenticatedPrincipal> principal;
        try {
            principal = sessionProvider.authenticate(token);
        } catch (RuntimeException infra) {
            log.error("authentication provider failure while validating bearer token", infra);
            dependencyUnavailable(request, response);
            return;
        }
        if (principal.isEmpty()) {
            reject(response, ErrorCode.SESSION_INVALID, "session token invalid or expired");
            return;
        }
        AuthenticatedPrincipal p = principal.get();
        // 快照不是充分认证依据：账号 disabled / auth_revision 递增 / credential_version
        // 轮换 → 旧 token 立即失效（oracle B2，单行查询无 JOIN/锁）。
        boolean valid;
        try {
            valid = revalidator.stillValid(p);
        } catch (RuntimeException infra) {
            log.error("principal revalidation failure (dependency unavailable)", infra);
            dependencyUnavailable(request, response);
            return;
        }
        if (!valid) {
            reject(response, ErrorCode.SESSION_INVALID,
                    "session no longer valid against local account/device state");
            return;
        }
        String requestId = String.valueOf(
                request.getAttribute(RequestIdFilter.ATTR_REQUEST_ID) == null
                        ? "" : request.getAttribute(RequestIdFilter.ATTR_REQUEST_ID));
        PrincipalContext ctx = switch (p.principalType()) {
            case APP -> PrincipalContext.forApp(p, requestId);
            case GIMBAL -> PrincipalContext.forGimbal(p, requestId);
        };
        request.setAttribute(ATTR_PRINCIPAL, ctx);
        MDC.put("principalType", p.principalType().name());
        MDC.put("principalRef", ctx.t13PrincipalId());
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("principalType");
            MDC.remove("principalRef");
        }
    }

    /** 认证拒绝：401，沿用 code 默认 retryable（不泄露细节）。 */
    private void reject(HttpServletResponse response, ErrorCode code, String message) throws IOException {
        ApiException ex = new ApiException(code, message);
        render(requestId(), response, code.name(), ex.getMessage(), ex.isRetryable(),
                HttpStatus.UNAUTHORIZED.value());
    }

    /** 基础设施故障（provider/revalidator 抛异常）：503 DEPENDENCY_UNAVAILABLE，可重试。 */
    private void dependencyUnavailable(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        render(EnvelopeSupport.requestId(request), response, ErrorCode.DEPENDENCY_UNAVAILABLE.name(),
                "authentication dependency unavailable; retry later", true,
                HttpStatus.SERVICE_UNAVAILABLE.value());
    }

    /** 统一信封渲染（复用 ErrorEnvelope 序列化路径；不输出堆栈/内部信息）。 */
    private void render(String requestId, HttpServletResponse response, String code, String message,
                        boolean retryable, int status) throws IOException {
        String id = requestId == null ? "" : requestId;
        ErrorEnvelope body = ErrorEnvelope.of(id, code, message, retryable, null);
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        if (!id.isBlank()) {
            response.setHeader(RequestIdFilter.HEADER, id);
        }
        objectMapper.writeValue(response.getOutputStream(), body);
    }

    private static String requestId() {
        String id = MDC.get(RequestIdFilter.MDC_KEY);
        return id == null ? "" : id;
    }
}

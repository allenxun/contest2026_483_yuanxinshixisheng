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

    public static final String ATTR_PRINCIPAL = "mvp.principal";

    /** 公开（无 Bearer）端点：method + 精确 path。 */
    private static final Set<String> PUBLIC = Set.of(
            "POST /api/v1/auth/sms-challenges",
            "POST /api/v1/auth/sessions",
            "POST /api/v1/auth/session-refreshes",
            "POST /api/v1/gimbal-sessions");

    private final SessionProvider sessionProvider;
    private final ObjectMapper objectMapper;

    public BearerAuthFilter(SessionProvider sessionProvider, ObjectMapper objectMapper) {
        this.sessionProvider = sessionProvider;
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
        Optional<AuthenticatedPrincipal> principal = sessionProvider.authenticate(token);
        if (principal.isEmpty()) {
            reject(response, ErrorCode.SESSION_INVALID, "session token invalid or expired");
            return;
        }
        AuthenticatedPrincipal p = principal.get();
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

    private void reject(HttpServletResponse response, ErrorCode code, String message) throws IOException {
        // ApiException → 信封字段统一走 code 默认值（401 不可重试）
        ApiException ex = new ApiException(code, message);
        String requestId = MDC.get(RequestIdFilter.MDC_KEY);
        ErrorEnvelope body = ErrorEnvelope.of(requestId == null ? "" : requestId,
                code.name(), ex.getMessage(), ex.isRetryable(), null);
        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getOutputStream(), body);
    }
}

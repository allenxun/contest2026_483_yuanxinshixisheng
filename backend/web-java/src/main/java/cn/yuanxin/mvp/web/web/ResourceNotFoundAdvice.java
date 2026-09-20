package cn.yuanxin.mvp.web.web;

import cn.yuanxin.mvp.web.error.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.Map;

/**
 * 未匹配路由（由 Spring ResourceHttpRequestHandler 抛出，handler bean 不在
 * 业务包内，主 advice 的 basePackages 不覆盖）→ 404 RESOURCE_NOT_VISIBLE
 * 标准信封：不泄露资源是否存在（DD 3.2），X-Request-Id 由过滤器保证。
 */
@RestControllerAdvice
public class ResourceNotFoundAdvice {

    private final EnvelopeSupport envelopes;

    public ResourceNotFoundAdvice(EnvelopeSupport envelopes) {
        this.envelopes = envelopes;
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Map<String, Object>> notFound(NoResourceFoundException ex,
                                                        HttpServletRequest request) {
        ErrorEnvelope body = envelopes.error(request, new ErrorEnvelope.ErrorBody(
                ErrorCode.RESOURCE_NOT_VISIBLE.name(), "resource not visible", false, null));
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                Map.of("requestId", body.requestId(),
                        "error", Map.of("code", body.error().code(),
                                "message", body.error().message(),
                                "retryable", body.error().retryable())));
    }
}

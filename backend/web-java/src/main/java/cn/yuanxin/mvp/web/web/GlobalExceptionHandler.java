package cn.yuanxin.mvp.web.web;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.StaleAttemptException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 全局异常 → 标准错误信封（DD 3.2；decisions #15）：
 * <ul>
 *   <li>ApiException → 其自带 code/status/retryable/details/headers（如 Retry-After）；</li>
 *   <li>Bean Validation / 类型转换 / 非法游标 → 400 INVALID_INPUT，
 *       details.fields 列出违规字段（仅调用方可见信息）；</li>
 *   <li>请求体 JSON 不可读（含 Jackson STRICT_DUPLICATE_DETECTION 拒绝的重复键）
 *       → 400 INVALID_INPUT；</li>
 *   <li>未映射路径 → 404 RESOURCE_NOT_VISIBLE（不泄露存在性）；</li>
 *   <li>StaleAttemptException（T13 代次守卫：接管已发生，本尝试的业务写已随
 *       事务回滚）→ 409 REQUEST_IN_PROGRESS + Retry-After（裁量：按"同键稍后
 *       重试"语义，而非 500）；</li>
 *   <li>其余一切 → 500 INTERNAL：堆栈只进服务端日志，客户端只见 requestId。</li>
 * </ul>
 * 405/415 无对应契约错误码，映射为 400 INVALID_INPUT（客户端调用错误，非服务端故障）。
 */
@RestControllerAdvice(basePackages = "cn.yuanxin.mvp.web")
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    private final EnvelopeSupport envelopes;
    private final ObjectMapper objectMapper;

    public GlobalExceptionHandler(EnvelopeSupport envelopes, ObjectMapper objectMapper) {
        this.envelopes = envelopes;
        this.objectMapper = objectMapper;
    }

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, Object>> apiException(ApiException ex, HttpServletRequest request) {
        return render(request, ex.getCode().name(), ex.getMessage(), ex.isRetryable(),
                ex.getDetails(), ex.getHttpStatus(), ex.getHeaders());
    }

    @ExceptionHandler(StaleAttemptException.class)
    public ResponseEntity<Map<String, Object>> staleAttempt(StaleAttemptException ex,
                                                            HttpServletRequest request) {
        log.warn("stale idempotency attempt rejected (business tx rolled back): {}", ex.getMessage());
        return render(request, ErrorCode.REQUEST_IN_PROGRESS.name(),
                "idempotency attempt was taken over; business changes rolled back", true,
                null, HttpStatus.CONFLICT.value(), Map.of("Retry-After", "1"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> validation(MethodArgumentNotValidException ex,
                                                          HttpServletRequest request) {
        List<Map<String, Object>> fields = new ArrayList<>();
        for (FieldError fe : ex.getBindingResult().getFieldErrors()) {
            fields.add(fieldEntry(fe.getField(), fe.getDefaultMessage()));
        }
        for (var ce : ex.getBindingResult().getGlobalErrors()) {
            fields.add(fieldEntry(ce.getObjectName(), ce.getDefaultMessage()));
        }
        return invalidInput(request, fields);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<Map<String, Object>> methodValidation(HandlerMethodValidationException ex,
                                                                HttpServletRequest request) {
        List<Map<String, Object>> fields = new ArrayList<>();
        ex.getAllValidationResults().forEach(r -> r.getResolvableErrors().forEach(e ->
                fields.add(fieldEntry(e instanceof FieldError fe ? fe.getField()
                        : r.getMethodParameter().getParameterName(), e.getDefaultMessage()))));
        return invalidInput(request, fields);
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<Map<String, Object>> constraintViolation(ConstraintViolationException ex,
                                                                   HttpServletRequest request) {
        List<Map<String, Object>> fields = new ArrayList<>();
        for (ConstraintViolation<?> v : ex.getConstraintViolations()) {
            fields.add(fieldEntry(v.getPropertyPath().toString(), v.getMessage()));
        }
        return invalidInput(request, fields);
    }

    @ExceptionHandler({HttpMessageNotReadableException.class,
            MissingServletRequestParameterException.class,
            MissingRequestHeaderException.class,
            MethodArgumentTypeMismatchException.class,
            IllegalArgumentException.class})
    public ResponseEntity<Map<String, Object>> badInput(Exception ex, HttpServletRequest request) {
        String reason = switch (ex) {
            case HttpMessageNotReadableException e -> "malformed_json";
            case MissingServletRequestParameterException e -> "missing_parameter:" + e.getParameterName();
            case MissingRequestHeaderException e -> "missing_header:" + e.getHeaderName();
            case MethodArgumentTypeMismatchException e -> "bad_parameter:" + e.getName();
            default -> "invalid_argument";
        };
        log.debug("rejected request input ({}): {}", reason, ex.getMessage());
        return render(request, ErrorCode.INVALID_INPUT.name(), "invalid request input",
                false, Map.of("reason", reason), HttpStatus.BAD_REQUEST.value(), Map.of());
    }

    @ExceptionHandler(CursorException.class)
    public ResponseEntity<Map<String, Object>> badCursor(CursorException ex, HttpServletRequest request) {
        return render(request, ErrorCode.INVALID_INPUT.name(), ex.getMessage(), false,
                Map.of("reason", "invalid_cursor"), HttpStatus.BAD_REQUEST.value(), Map.of());
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, Object>> tooLarge(MaxUploadSizeExceededException ex,
                                                        HttpServletRequest request) {
        return render(request, ErrorCode.UPLOAD_TOO_LARGE.name(), "upload exceeds configured limit",
                false, null, HttpStatus.PAYLOAD_TOO_LARGE.value(), Map.of());
    }

    @ExceptionHandler({HttpRequestMethodNotSupportedException.class,
            HttpMediaTypeNotSupportedException.class})
    public ResponseEntity<Map<String, Object>> methodOrMedia(Exception ex, HttpServletRequest request) {
        return render(request, ErrorCode.INVALID_INPUT.name(), "unsupported request shape", false,
                Map.of("reason", ex instanceof HttpRequestMethodNotSupportedException
                        ? "method_not_allowed" : "unsupported_media_type"),
                HttpStatus.BAD_REQUEST.value(), Map.of());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> unexpected(Exception ex, HttpServletRequest request) {
        log.error("unhandled exception on {} {}", request.getMethod(), request.getRequestURI(), ex);
        return render(request, ErrorCode.INTERNAL.name(), "internal server error",
                false, null, HttpStatus.INTERNAL_SERVER_ERROR.value(), Map.of());
    }

    private ResponseEntity<Map<String, Object>> invalidInput(HttpServletRequest request,
                                                             List<Map<String, Object>> fields) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("fields", fields);
        return render(request, ErrorCode.INVALID_INPUT.name(), "request validation failed",
                false, details, HttpStatus.BAD_REQUEST.value(), Map.of());
    }

    private Map<String, Object> fieldEntry(String field, String reason) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("field", field);
        m.put("reason", reason == null ? "invalid" : reason);
        return m;
    }

    private ResponseEntity<Map<String, Object>> render(HttpServletRequest request, String code,
                                                       String message, boolean retryable,
                                                       Map<String, Object> details, int status,
                                                       Map<String, String> headers) {
        ErrorEnvelope body = envelopes.error(request,
                new ErrorEnvelope.ErrorBody(code, message, retryable, details));
        // 保证无循环序列化风险：信封转普通 Map 输出
        Map<String, Object> map = objectMapper.convertValue(body, Map.class);
        org.springframework.http.HttpHeaders httpHeaders = new org.springframework.http.HttpHeaders();
        headers.forEach(httpHeaders::set);
        return new ResponseEntity<>(map, httpHeaders, org.springframework.http.HttpStatus.valueOf(status));
    }
}

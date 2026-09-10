package cn.yuanxin.mvp.web.error;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * 结构化业务异常（错误信封的唯一生产路径）。
 *
 * <p>携带 code / HTTP 状态 / retryable / details（只含调用方可见的冲突字段、
 * 缺失序号等；不泄露供应商诊断、堆栈、人脸候选）与附加响应头
 * （如 REQUEST_IN_PROGRESS 的 Retry-After）。</p>
 */
public class ApiException extends RuntimeException {

    private final ErrorCode code;
    private final int httpStatus;
    private final boolean retryable;
    private final Map<String, Object> details;
    private final Map<String, String> headers;

    public ApiException(ErrorCode code, String message) {
        this(code, code.defaultStatus().value(), code.defaultRetryable(), message, null, null);
    }

    public ApiException(ErrorCode code, String message, Map<String, Object> details) {
        this(code, code.defaultStatus().value(), code.defaultRetryable(), message, details, null);
    }

    public ApiException(ErrorCode code, int httpStatus, String message,
                        Map<String, Object> details, Map<String, String> headers) {
        this(code, httpStatus, code.defaultRetryable(), message, details, headers);
    }

    public ApiException(ErrorCode code, int httpStatus, boolean retryable, String message,
                        Map<String, Object> details, Map<String, String> headers) {
        super(message, null, true, false); // 不进客户端；堆栈只留在服务端日志（advice 记录）
        this.code = Objects.requireNonNull(code);
        this.httpStatus = httpStatus;
        this.retryable = retryable;
        this.details = details == null ? null : Collections.unmodifiableMap(new LinkedHashMap<>(details));
        this.headers = headers == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(headers));
    }

    public ErrorCode getCode() {
        return code;
    }

    public int getHttpStatus() {
        return httpStatus;
    }

    public boolean isRetryable() {
        return retryable;
    }

    public Map<String, Object> getDetails() {
        return details;
    }

    public Map<String, String> getHeaders() {
        return headers;
    }

    /** 带 Retry-After 秒数的 REQUEST_IN_PROGRESS。 */
    public static ApiException requestInProgress(long retryAfterSeconds) {
        long ra = Math.max(1, retryAfterSeconds);
        return new ApiException(ErrorCode.REQUEST_IN_PROGRESS,
                ErrorCode.REQUEST_IN_PROGRESS.defaultStatus().value(),
                "previous attempt still in progress; retry with the same Idempotency-Key after Retry-After",
                Map.of("retryAfterSeconds", ra),
                Map.of("Retry-After", String.valueOf(ra)));
    }
}

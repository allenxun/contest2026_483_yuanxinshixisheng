package cn.yuanxin.mvp.web.error;

import org.springframework.http.HttpStatus;

/**
 * 稳定业务原因码（DD 3.2 错误码表 + 基础层扩展 NOT_IMPLEMENTED + 500 INTERNAL）。
 *
 * <p>枚举取值与 backend/contracts/openapi/openapi.yaml components.schemas.ErrorCode
 * 一致（INTERNAL 在 OpenAPI ErrorEnvelope 响应用散文描述，500 样例见 DD 3.2）；
 * INTERNAL 只用于未映射异常，不出现在业务端点 x-error-codes 中。</p>
 *
 * <p>retryable 语义（digest §3 / DD 3.2 重试动作列）：429/503/504 与
 * REQUEST_IN_PROGRESS（同逻辑键等待重试）为 true；其余为 false。
 * INTERNAL 取 false——未知异常不承诺重试安全，客户端按 requestId 诊断。</p>
 */
public enum ErrorCode {
    // 400 / 413 / 415 / 422
    INVALID_INPUT(HttpStatus.BAD_REQUEST, false),
    UPLOAD_TOO_LARGE(HttpStatus.PAYLOAD_TOO_LARGE, false),
    UNSUPPORTED_IMAGE(HttpStatus.UNSUPPORTED_MEDIA_TYPE, false),
    FACE_QUALITY_REJECTED(HttpStatus.UNPROCESSABLE_ENTITY, false),
    // 401
    AUTH_REQUIRED(HttpStatus.UNAUTHORIZED, false),
    SESSION_INVALID(HttpStatus.UNAUTHORIZED, false),
    // 403 / 404
    RESOURCE_NOT_VISIBLE(HttpStatus.NOT_FOUND, false),
    CALLER_NOT_ALLOWED(HttpStatus.FORBIDDEN, false),
    FACE_NOT_VERIFIED(HttpStatus.FORBIDDEN, false),
    GRANT_REVOKED(HttpStatus.FORBIDDEN, false),
    // 409
    IDEMPOTENCY_CONTENT_CONFLICT(HttpStatus.CONFLICT, false),
    BINDING_CHANGED(HttpStatus.CONFLICT, false),
    TASK_REPLACED(HttpStatus.CONFLICT, false),
    PHOTO_VERSION_CONFLICT(HttpStatus.CONFLICT, false),
    DEVICE_OCCUPIED(HttpStatus.CONFLICT, false),
    PLAN_NOT_READY(HttpStatus.CONFLICT, false),
    PLAN_COMPLETED(HttpStatus.CONFLICT, false),
    EXECUTION_NOT_RESUMABLE(HttpStatus.CONFLICT, false),
    RECORD_CONFLICT(HttpStatus.CONFLICT, false),
    CLOSURE_GAPS(HttpStatus.CONFLICT, false),
    STOP_NOT_CONFIRMED(HttpStatus.CONFLICT, false),
    BOUND_TO_OTHER(HttpStatus.CONFLICT, false),
    REQUEST_IN_PROGRESS(HttpStatus.CONFLICT, true),
    // 429 / 503 / 504 / 500 / 501
    RATE_LIMITED(HttpStatus.TOO_MANY_REQUESTS, true),
    DEPENDENCY_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, true),
    DEPENDENCY_TIMEOUT(HttpStatus.GATEWAY_TIMEOUT, true),
    INTERNAL(HttpStatus.INTERNAL_SERVER_ERROR, false),
    UNSUPPORTED_CONTRACT(HttpStatus.UNPROCESSABLE_ENTITY, false),
    NOT_IMPLEMENTED(HttpStatus.NOT_IMPLEMENTED, false);

    private final HttpStatus defaultStatus;
    private final boolean defaultRetryable;

    ErrorCode(HttpStatus defaultStatus, boolean defaultRetryable) {
        this.defaultStatus = defaultStatus;
        this.defaultRetryable = defaultRetryable;
    }

    public HttpStatus defaultStatus() {
        return defaultStatus;
    }

    public boolean defaultRetryable() {
        return defaultRetryable;
    }
}

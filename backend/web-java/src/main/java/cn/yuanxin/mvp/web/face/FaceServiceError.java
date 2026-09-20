package cn.yuanxin.mvp.web.face;

/**
 * 远端人脸服务错误信封中的错误信息（{@code {"error":{...}}}）。
 *
 * @param code      服务错误码（如 {@code NO_FACE}/{@code SUBJECT_NOT_FOUND}）
 * @param message   服务消息（不含我方 token/图像；可安全记录）
 * @param retryable 服务声明的可重试性
 * @param requestId 服务请求 id（诊断用）
 * @param httpStatus HTTP 状态码（本地捕获）
 */
public record FaceServiceError(
        String code,
        String message,
        boolean retryable,
        String requestId,
        int httpStatus) {

    public String safeCode() {
        return code == null || code.isBlank() ? "<none>" : code;
    }
}

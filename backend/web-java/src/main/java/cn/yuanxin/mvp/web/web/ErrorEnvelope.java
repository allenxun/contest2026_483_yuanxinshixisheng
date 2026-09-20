package cn.yuanxin.mvp.web.web;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.Map;

/**
 * 错误响应信封（contracts ErrorEnvelope）：
 * {@code {requestId, error:{code, message, retryable, details?}}}。
 *
 * <p>details 只含调用方可见的冲突字段/缺失序号；不泄露归属、人脸候选、
 * 供应商诊断、堆栈（DD 3.2、A/decisions #15）。</p>
 */
public record ErrorEnvelope(String requestId, ErrorBody error) {

    public record ErrorBody(String code, String message, boolean retryable,
                            @JsonInclude(JsonInclude.Include.NON_NULL) Map<String, Object> details) {
    }

    public static ErrorEnvelope of(String requestId, String code, String message,
                                   boolean retryable, Map<String, Object> details) {
        return new ErrorEnvelope(requestId, new ErrorBody(code, message, retryable, details));
    }
}

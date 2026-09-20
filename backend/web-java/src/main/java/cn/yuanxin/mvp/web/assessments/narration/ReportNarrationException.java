package cn.yuanxin.mvp.web.assessments.narration;

/**
 * 报告播报下游失败（类型化）。<b>绝不</b>承载评分值、区域值、播报文本或 API Key：
 * {@link #getMessage()} 只使用固定安全文案，HTTP 状态/下游业务码仅用于服务端日志。
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiException} 同源范式、刻意不共享。</p>
 *
 * <p>任何失败都不得回退为替身或合成文案——上层见此异常必须返回依赖类问题或流内 error 终态。</p>
 */
public class ReportNarrationException extends RuntimeException {

    private final ReportNarrationFailureKind kind;
    private final Integer httpStatus;
    private final String safeCode;

    public ReportNarrationException(ReportNarrationFailureKind kind, String message) {
        this(kind, message, null, null);
    }

    public ReportNarrationException(ReportNarrationFailureKind kind, String message, Integer httpStatus,
                                    String safeCode) {
        super(message);
        this.kind = kind;
        this.httpStatus = httpStatus;
        this.safeCode = safeCode;
    }

    public ReportNarrationFailureKind kind() {
        return kind;
    }

    /** 下游 HTTP 状态；无（传输失败）时为 null。 */
    public Integer httpStatus() {
        return httpStatus;
    }

    /** 下游 problem+json 的 {@code code}（经白名单归一）；仅用于日志。 */
    public String safeCode() {
        return safeCode;
    }
}

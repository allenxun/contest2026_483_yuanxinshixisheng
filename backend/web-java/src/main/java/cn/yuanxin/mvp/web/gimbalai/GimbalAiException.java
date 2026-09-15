package cn.yuanxin.mvp.web.gimbalai;

/**
 * 云台 AI 下游失败（类型化）。<b>绝不</b>承载用户文本或 API Key：{@link #getMessage()}
 * 只使用固定安全文案，HTTP 状态/下游业务码仅用于服务端日志。
 *
 * <p>任何失败都不得回退为替身或合成答案——上层见此异常必须返回依赖类问题。</p>
 */
public class GimbalAiException extends RuntimeException {

    private final GimbalAiFailureKind kind;
    private final Integer httpStatus;
    private final String safeCode;

    public GimbalAiException(GimbalAiFailureKind kind, String message) {
        this(kind, message, null, null);
    }

    public GimbalAiException(GimbalAiFailureKind kind, String message, Integer httpStatus,
                             String safeCode) {
        super(message);
        this.kind = kind;
        this.httpStatus = httpStatus;
        this.safeCode = safeCode;
    }

    public GimbalAiFailureKind kind() {
        return kind;
    }

    /** 下游 HTTP 状态；无（传输失败）时为 null。 */
    public Integer httpStatus() {
        return httpStatus;
    }

    /** 下游 problem+json 的 {@code code}（若可解析）；仅用于日志。 */
    public String safeCode() {
        return safeCode;
    }
}

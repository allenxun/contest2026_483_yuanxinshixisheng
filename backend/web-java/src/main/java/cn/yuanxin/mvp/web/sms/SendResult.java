package cn.yuanxin.mvp.web.sms;

/**
 * 一次短信发送的受理结果。
 *
 * <p><b>语义要点：</b>{@link #accepted()} 为 {@code true} 当且仅当阿里云响应体业务
 * {@code Code} <b>严格等于</b> {@code "OK"}；这仅代表平台<b>受理</b>，不代表用户已收到
 * 或已送达。HTTP 200 / 异常与否都不作为成功判据。</p>
 *
 * <p>{@link #code()}/{@link #message()}/{@link #requestId()}/{@link #bizId()} 为平台回执
 * 字段，可安全记录（不含量产验证码/凭据/完整手机号）。</p>
 */
public record SendResult(
        boolean accepted,
        String code,
        String message,
        String requestId,
        String bizId,
        FailureKind failureKind) {

    /** 平台受理（Code=OK）。 */
    public static SendResult accepted(String code, String message, String requestId, String bizId) {
        return new SendResult(true, code, message, requestId, bizId, null);
    }

    /** 平台拒绝或异常；{@code kind} 为空时保守归为 {@link FailureKind#DEPENDENCY}。 */
    public static SendResult failed(FailureKind kind, String code, String message,
                                    String requestId, String bizId) {
        return new SendResult(false, code, message, requestId, bizId,
                kind == null ? FailureKind.DEPENDENCY : kind);
    }
}

package cn.yuanxin.mvp.web.assessments.narration;

/**
 * 报告播报下游失败分类：由 HTTP 客户端按"传输/响应形状"归类，供服务层映射到既有错误码。
 * 绝不携带评分值、区域值或密钥。
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiFailureKind} 同源范式、刻意不共享：共享需改动已交付
 * 并经审的 {@code web/gimbalai/**}，风险与范围都不可接受；未来若出现第三处再统一抽取。</p>
 */
public enum ReportNarrationFailureKind {

    /** 2xx 但响应不是合法 SSE / 事件缺必填字段 / 终态纪律违规（上游契约违约）。 */
    MALFORMED,

    /** 连接/传输失败，或下游返回非 2xx（含 problem+json）。 */
    UNAVAILABLE,

    /** 连接或读取超时。 */
    TIMEOUT
}

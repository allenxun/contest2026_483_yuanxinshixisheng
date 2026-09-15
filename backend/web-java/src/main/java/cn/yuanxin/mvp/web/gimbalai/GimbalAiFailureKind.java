package cn.yuanxin.mvp.web.gimbalai;

/**
 * 云台 AI 下游失败分类：由 HTTP 客户端按"传输/响应形状"归类，供服务层映射到
 * 既有错误码。绝不携带用户文本或密钥。
 */
public enum GimbalAiFailureKind {

    /** 2xx 但响应不是合法 JSON / 缺 {@code answer.text} / 类型不符（上游契约违约）。 */
    MALFORMED,

    /** 连接/传输失败，或下游返回非 2xx（含 problem+json）。 */
    UNAVAILABLE,

    /** 连接或读取超时。 */
    TIMEOUT
}

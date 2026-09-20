package cn.yuanxin.mvp.web.web;

/**
 * 成功响应信封（contracts/openapi/openapi.yaml components.schemas.SuccessEnvelope）：
 * {@code {requestId, data, meta:{replayed, serverTime}}}。
 *
 * <p>204 不携带本信封（requestId 走 X-Request-Id 头，见 RequestIdFilter）。
 * meta 容忍新增字段（契约 EnvelopeMeta additionalProperties:true）；
 * data 由各端点显式给出（列表端点用 {@link ListData}）。</p>
 */
public record SuccessEnvelope(String requestId, Object data, Meta meta) {

    /** @param replayed true 表示本响应来自 T13 幂等重放（原业务结果，不重做写入） */
    public record Meta(boolean replayed, String serverTime) {
    }

    public static SuccessEnvelope of(String requestId, Object data, boolean replayed, String serverTime) {
        return new SuccessEnvelope(requestId, data, new Meta(replayed, serverTime));
    }
}

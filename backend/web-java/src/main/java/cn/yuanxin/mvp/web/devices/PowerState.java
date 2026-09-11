package cn.yuanxin.mvp.web.devices;

/**
 * M2-A02 心跳上报的 {@code powerState}（契约枚举 {@code [awake, asleep]}）。
 *
 * <p>常量刻意使用小写以与契约 JSON 文本逐字一致（Jackson 按 {@code name()}
 * 序列化/反序列化）；未知取值由 Jackson 反序列化失败 → 400 INVALID_INPUT。</p>
 */
public enum PowerState {
    awake,
    asleep
}

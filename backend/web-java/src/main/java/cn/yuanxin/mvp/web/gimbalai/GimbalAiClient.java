package cn.yuanxin.mvp.web.gimbalai;

/**
 * 云台 AI 文本问答下游端口（SSE 流式）。
 *
 * <p>无状态、无上下文：当前增量<b>不</b>存储会话历史/continuation_state，且绝不断点续传。</p>
 */
public interface GimbalAiClient {

    /**
     * 打开下游 {@code POST /internal/v1/ai/responses:stream} 流。
     *
     * <p><b>预流失败</b>（连接失败、预流非 2xx、预流超时）在返回前抛 {@link GimbalAiException}，
     * 上层据此返回 JSON problem（HTTP 映射）；<b>流内失败</b>由 {@link GimbalAiStream#next()}
     * 抛 {@link GimbalAiException}。</p>
     *
     * @param text 已通过 bean validation 的用户文本
     * @return 已校验的增量事件流
     * @throws GimbalAiException 预流失败；<b>绝不</b>回退一次性接口、绝不合成答案
     */
    GimbalAiStream openStream(String text);
}

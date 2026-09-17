package cn.yuanxin.mvp.web.assessments.narration;

/**
 * 报告播报下游端口（SSE 流式）。
 *
 * <p>无状态、无本地幂等存储：每次调用生成全新的 {@code X-Request-Id}/{@code Idempotency-Key}，
 * <b>客户端重试即一次新评估</b>（下游亦无重放存储）；绝不断点续传。</p>
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiClient} 同源范式、刻意不共享。</p>
 */
public interface ReportNarrationClient {

    /**
     * 打开下游 {@code POST {base-url}/internal/v1/weijing/reports/assess:stream} 流。
     *
     * <p><b>预流失败</b>（连接失败、预流非 2xx、预流超时）在返回前抛
     * {@link ReportNarrationException}，上层据此返回 JSON problem（HTTP 映射）；
     * <b>流内失败</b>由 {@link ReportNarrationStream#next()} 抛 {@link ReportNarrationException}。</p>
     *
     * @param scores 已校验并白名单化的三项评分（{@code pores}/{@code spots}/{@code surface_gloss}）
     * @return 已校验的增量事件流
     * @throws ReportNarrationException 预流失败；<b>绝不</b>回退一次性接口、绝不合成文案
     */
    ReportNarrationStream openStream(ReportNarrationScores scores);
}

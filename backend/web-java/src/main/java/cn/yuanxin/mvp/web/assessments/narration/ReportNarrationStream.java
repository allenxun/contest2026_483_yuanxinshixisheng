package cn.yuanxin.mvp.web.assessments.narration;

/**
 * 已建立的下游 SSE 流句柄（{@link ReportNarrationClient#openStream} 成功返回后）。
 *
 * <p>{@link #next()} 增量返回已校验事件；终态后返回 {@code null}。{@link #close()}
 * 取消下游连接（客户端断开时必须调用）。</p>
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiStream} 同源范式、刻意不共享。</p>
 */
public interface ReportNarrationStream extends AutoCloseable {

    /** @return 下一事件；终态后（或已关闭）返回 {@code null} */
    ReportNarrationEvent next();

    @Override
    void close();
}

package cn.yuanxin.mvp.web.assessments.narration;

/**
 * SSE 行源：每次返回一行（不含行尾），流结束返回 {@code null}；读取超时/传输失败由
 * 实现抛 {@link ReportNarrationException}。{@link #close()} 必须能解除阻塞的读取并取消下游连接。
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiLineSource} 同源范式、刻意不共享。</p>
 */
interface ReportNarrationLineSource extends AutoCloseable {

    /** @return 下一行（不含行尾）；{@code null} 表示流正常结束 */
    String readLine();

    @Override
    void close();
}

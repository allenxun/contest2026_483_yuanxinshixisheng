package cn.yuanxin.mvp.web.gimbalai;

/**
 * SSE 行源：每次返回一行（不含行尾），流结束返回 {@code null}；读取超时/传输失败由
 * 实现抛 {@link GimbalAiException}。{@link #close()} 必须能解除阻塞的读取并取消下游连接。
 */
interface GimbalAiLineSource extends AutoCloseable {

    /** @return 下一行（不含行尾）；{@code null} 表示流正常结束 */
    String readLine();

    @Override
    void close();
}

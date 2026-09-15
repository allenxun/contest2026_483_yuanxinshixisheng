package cn.yuanxin.mvp.web.gimbalai;

/**
 * 已建立的下游 SSE 流句柄（{@link GimbalAiClient#openStream(String)} 成功返回后）。
 *
 * <p>{@link #next()} 增量返回已校验事件；终态后返回 {@code null}。{@link #close()}
 * 取消下游连接（客户端断开时必须调用）。</p>
 */
public interface GimbalAiStream extends AutoCloseable {

    /** @return 下一事件；终态后（或已关闭）返回 {@code null} */
    GimbalAiEvent next();

    @Override
    void close();
}

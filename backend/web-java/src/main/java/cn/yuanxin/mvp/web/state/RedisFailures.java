package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.RedisSystemException;

/**
 * Redis 状态后端故障的<b>唯一</b>翻译点（fail closed）。
 *
 * <p><b>三条硬纪律</b>：</p>
 * <ol>
 *   <li><b>任何后端故障都不得被吞成 {@code Optional.empty()}</b>。那会把"依赖不可用"伪装成
 *       "会话无效 / 验证码错误 / refresh 无效"（401），既掩盖故障又违反 fail-closed；</li>
 *   <li><b>绝不回退内存实现制造伪成功</b>：{@code app.state.provider=redis} 时不存在内存兜底路径；</li>
 *   <li><b>本地 API 误用不是依赖故障</b>：{@code InvalidDataAccessApiUsageException} 等
 *       属代码缺陷，必须原样抛出（由 {@code GlobalExceptionHandler} 落到 500 {@code INTERNAL}），
 *       不得伪装成 503 让运维误判为"Redis 挂了"。</li>
 * </ol>
 *
 * <p><b>为什么统一 503 {@code DEPENDENCY_UNAVAILABLE} 而不用 504 {@code DEPENDENCY_TIMEOUT}</b>：
 * 命令超时在语义上更接近 504，但既有 HTTP 契约（{@code backend/contracts/openapi/openapi.yaml}
 * 的各操作 {@code responses} 与 {@code x-error-codes}）<b>没有</b>声明 504；引入它等于改变对外契约，
 * 而本轮硬要求是"保持全部 HTTP 契约"。同时 {@code BearerAuthFilter} 既有行为就是把 provider 抛出的
 * {@code RuntimeException} 渲染为 503 {@code DEPENDENCY_UNAVAILABLE} 信封，故 503 也是<b>与现状一致</b>
 * 的选择。该取舍如实记录在 {@code backend/handoffs/B-redis-state-migration.md} §6。</p>
 *
 * <p><b>脱敏</b>：返回给客户端的消息是<b>固定文案 + 操作名</b>，绝不包含 Redis 主机、端口、口令、
 * 键名、token、手机号或验证码。服务端日志记 {@code operation} + 异常类名 + 异常消息
 * （Redis 异常消息不含口令：认证失败为 {@code WRONGPASS invalid username-password pair}，
 * 不回显秘密；键名本身已是摘要而非原文）。</p>
 */
public final class RedisFailures {

    private static final Logger log = LoggerFactory.getLogger(RedisFailures.class);

    private RedisFailures() {
    }

    /**
     * 是否为"状态后端不可用"（连接失败 / 命令超时 / 服务端错误如认证失败、READONLY、
     * {@code ERR DB index is out of range}、OOM 拒命令）。
     */
    public static boolean isStoreUnavailable(Throwable throwable) {
        return throwable instanceof RedisConnectionFailureException
                || throwable instanceof QueryTimeoutException
                || throwable instanceof RedisSystemException;
    }

    /**
     * 把状态后端故障翻译成 fail-closed 的 {@link ApiException}（503
     * {@link ErrorCode#DEPENDENCY_UNAVAILABLE}）；<b>非</b>后端故障原样返回，由调用方抛出。
     *
     * <p>消息明确写出"请求未被处理"，避免客户端把 503 误读为"凭据无效"或"操作已成功"。</p>
     *
     * @param operation 内部操作名（如 {@code authenticate}、{@code verify-challenge}）；
     *                  仅用于诊断，不含任何凭据或 PII
     * @param ex        捕获到的运行时异常
     */
    public static RuntimeException failClosed(String operation, RuntimeException ex) {
        if (!isStoreUnavailable(ex)) {
            return ex;
        }
        log.warn("state store unavailable operation={} cause={} detail={}", operation,
                ex.getClass().getName(), ex.getMessage());
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "session/verification state store is unavailable; the request was NOT processed"
                        + " and no credential was accepted or consumed (operation=" + operation + ")");
    }

    /**
     * 便捷包装：执行一段状态后端访问，把后端故障翻译成 fail-closed 的 503。
     * 业务判定（验证码错误、会话不存在等）必须以正常返回值表达，<b>不得</b>借异常通道，
     * 以免被本方法误判为后端故障。
     */
    public static <T> T call(String operation, java.util.function.Supplier<T> action) {
        try {
            return action.get();
        } catch (RuntimeException ex) {
            throw failClosed(operation, ex);
        }
    }
}

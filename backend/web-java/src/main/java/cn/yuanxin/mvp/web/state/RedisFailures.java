package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.RedisSystemException;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

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
 * 键名、token、手机号或验证码。服务端日志只记 {@code operation}、异常类名与一个
 * <b>白名单提取</b>的服务端错误词（命中固定词才记，否则 {@code <unclassified>}）；
 * <b>绝不</b>记录任何异常 {@code getMessage()}。原因：连接/超时类消息常含 {@code host:port}，
 * 而 {@code RedisSystemException} 并不保证只包装纯服务端 {@code ERR}（未知 driver 异常可能携带
 * 拓扑或底层详情），因此对全部三类异常一视同仁地脱敏。</p>
 */
public final class RedisFailures {

    private static final Logger log = LoggerFactory.getLogger(RedisFailures.class);

    /** 允许写入日志的固定服务端错误词（严格白名单；命中才记，否则 {@code <unclassified>}）。 */
    private static final List<Pattern> SERVER_CODE_PATTERNS = List.of(
            Pattern.compile("DB index is out of range"),
            Pattern.compile("\\bREADONLY\\b"),
            Pattern.compile("\\bOOM\\b"),
            Pattern.compile("\\bWRONGPASS\\b"),
            Pattern.compile("\\bCROSSSLOT\\b"),
            Pattern.compile("\\bNOAUTH\\b"),
            Pattern.compile("\\bNOPERM\\b"),
            Pattern.compile("\\bWRONGTYPE\\b"),
            Pattern.compile("\\bNOSCRIPT\\b"),
            Pattern.compile("\\bBUSY\\b"));

    private static final String UNCLASSIFIED_CODE = "<unclassified>";

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
        // 脱敏（对全部三类异常一致）：日志只含 operation、异常类名与白名单错误词；
        // 绝不记录 ex.getMessage()（连接/超时类常含 host:port；RedisSystemException 也可能
        // 携带拓扑或底层详情）。需要可诊断性时只从 message/cause 中提取固定白名单词。
        log.warn("state store unavailable operation={} cause={} serverCode={}",
                operation, ex.getClass().getName(), whitelistedServerCode(ex));
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "session/verification state store is unavailable; the request was NOT processed"
                        + " and no credential was accepted or consumed (operation=" + operation + ")");
    }

    /**
     * 从异常及其 cause 链的 message 中提取<b>固定白名单</b>服务端错误词；未命中返回
     * {@code <unclassified>}。提取到的词本身不带拓扑/口令信息，可安全写日志。
     * 注意：本方法只读取 message 用于匹配，<b>绝不</b>把它返回或写日志。
     */
    static String whitelistedServerCode(RuntimeException ex) {
        StringBuilder haystack = new StringBuilder();
        Throwable current = ex;
        for (int depth = 0; current != null && depth < 8; depth++) {
            String message = current.getMessage();
            if (message != null && !message.isBlank()) {
                haystack.append(message).append('\n');
            }
            Throwable next = current.getCause();
            if (next == current) {
                break;
            }
            current = next;
        }
        String text = haystack.toString();
        for (Pattern pattern : SERVER_CODE_PATTERNS) {
            Matcher matcher = pattern.matcher(text);
            if (matcher.find()) {
                return matcher.group();
            }
        }
        return UNCLASSIFIED_CODE;
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

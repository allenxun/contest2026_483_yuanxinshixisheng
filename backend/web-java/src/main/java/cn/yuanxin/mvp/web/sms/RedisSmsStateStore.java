package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.state.RedisFailures;
import cn.yuanxin.mvp.web.state.StateKeys;

import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * Redis 短信状态存储（{@code app.state.provider=redis}）：跨实例一致、重启不丢、fail closed。
 *
 * <p><b>全部原子步由 Lua 完成</b>（脚本位于 {@code src/main/resources/redis/sms-*.lua}，
 * 以不可变单例 {@link DefaultRedisScript} 加载；所有键经 {@link StateKeys} 构造，脚本访问的
 * 每个键都通过 {@code KEYS[]} 传入）：</p>
 * <ol>
 *   <li>创建 challenge：{@code HSET + EXPIRE} 一次完成且仅当键不存在；</li>
 *   <li>一次性核销：过期判定 + 尝试上限 + 摘要比较 + 计数或删除 + 返回手机号，单个脚本；</li>
 *   <li>节流预留：三窗口检查 + 占用 + 首次设 TTL，单个脚本；</li>
 *   <li>节流补偿：三窗口原子回退。</li>
 * </ol>
 *
 * <p><b>验证码明文绝不落 Redis</b>：只存 {@link StateKeys#codeDigest(String, String)}
 * （{@code sha256(code + "|" + challengeId)}，以 challengeId 为盐）。手机号是值中唯一的 PII
 * （核销成功需返回它建会话），绝不入键、绝不入日志。</p>
 *
 * <p><b>节流语义精化（有意，如实披露）</b>：旧实现只在发送<b>被受理后</b>计数，并靠进程内条带锁把
 * "预检 → 发送 → 记录" 串行化。跨实例无法用锁串行化，故本实现改为<b>原子预留 + 失败补偿</b>：
 * {@link #reserveSend} 原子占用三窗口名额（并发下绝不超发），远端发送未被受理时
 * {@link #releaseSend} 用另一脚本原子回退。稳态计数仍等于受理成功的发送数；差别仅在
 * "发送失败瞬间名额被短暂占用"，方向更严格。详见 {@code B-redis-state-migration.md} §4。</p>
 *
 * <p><b>失败计数 TTL</b>：限流计数键的 {@code INCR} 与 {@code if n==1 then EXPIRE} 在<b>同一脚本</b>内，
 * 因此绝不会留下 {@code TTL=-1} 的永不过期键；补偿使用 {@code EXISTS} 守卫，绝不制造负计数键。
 * challenge 的尝试计数是同哈希的 {@code att} 字段，随 challenge 键的 TTL 一起过期。</p>
 *
 * <p><b>fail closed</b>：所有后端访问经 {@link RedisFailures#call}；任何 Redis 连接/超时/服务端
 * 异常都翻译为 503 {@code DEPENDENCY_UNAVAILABLE}，绝不吞成 {@code Optional.empty()}（那会伪装成
 * 401 "验证码错误"），绝不回退内存制造伪成功。</p>
 *
 * <p><b>容量上限的等价处置（如实披露）</b>：内存实现用 {@code maxChallenges}/{@code maxTrackedPhones}
 * 计数上限对抗"内存只增不减"；Redis 后端每个键都有 TTL，该动因消失，故本实现不设应用层计数上限，
 * 改由键 TTL + 运维侧 Redis {@code maxmemory}/eviction 策略承载。若生产 Redis 触发 eviction，
 * 限流计数可能偏松（键被淘汰＝计数丢失）；生产应为该类键使用 {@code noeviction} 或独立实例并配置
 * 告警（设计文档 §5）。</p>
 */
public final class RedisSmsStateStore implements SmsStateStore {

    /** 核销成功时 Lua 返回值前缀，后接手机号；失败返回 {@code "!"}。返回值永远是字符串。 */
    private static final String CONSUME_SUCCESS_PREFIX = "+";
    private static final String CONSUME_FAILURE = "!";

    /**
     * 用于"空/空白验证码"的哨兵摘要：不等于任何 {@code sha256} 十六进制摘要，
     * 从而在 Lua 内表现为摘要不匹配（与旧实现 code==null 时匹配失败、尝试次数 +1 一致）。
     */
    private static final String NO_MATCH_DIGEST = "!no-match!";

    private static final DefaultRedisScript<Long> RESERVE_SCRIPT =
            script("redis/sms-rate-limit-reserve.lua", Long.class);
    private static final DefaultRedisScript<Long> COMPENSATE_SCRIPT =
            script("redis/sms-rate-limit-compensate.lua", Long.class);
    private static final DefaultRedisScript<Long> CREATE_SCRIPT =
            script("redis/sms-challenge-create.lua", Long.class);
    private static final DefaultRedisScript<String> CONSUME_SCRIPT =
            script("redis/sms-challenge-consume.lua", String.class);

    private final StringRedisTemplate template;
    private final StateKeys keys;
    private final SmsRiskProperties risk;

    public RedisSmsStateStore(StringRedisTemplate template, StateKeys keys, SmsRiskProperties risk) {
        this.template = template;
        this.keys = keys;
        this.risk = risk;
    }

    @Override
    public SendReservation reserveSend(String phone, Instant now) {
        SmsThrottleWindows.Snapshot windows = SmsThrottleWindows.compute(now);
        List<String> windowKeys = List.of(
                keys.smsRateLimit(phone, "m", windows.minuteBucket()),
                keys.smsRateLimit(phone, "h", windows.hourBucket()),
                keys.smsRateLimit(phone, "d", windows.dayBucket()));
        Long result = RedisFailures.call("sms-rate-limit-reserve", () -> template.execute(
                RESERVE_SCRIPT, windowKeys,
                String.valueOf(risk.maxPerMinute()), String.valueOf(risk.maxPerHour()),
                String.valueOf(risk.maxPerDay()),
                String.valueOf(windows.minuteTtlSeconds()), String.valueOf(windows.hourTtlSeconds()),
                String.valueOf(windows.dayTtlSeconds()),
                String.valueOf(windows.minuteRetryAfterSeconds()),
                String.valueOf(windows.hourRetryAfterSeconds()),
                String.valueOf(windows.dayRetryAfterSeconds())));
        long retryAfter = retryAfterFromScriptResult(result);
        if (retryAfter == 0L) {
            return SendReservation.granted(phone, windowKeys);
        }
        return SendReservation.throttled(retryAfter);
    }

    @Override
    public void commitSend(SendReservation reservation, Instant now) {
        // 预留即计数：受理成功后无需再写（稳态计数 = 受理成功的发送数）。
    }

    @Override
    public void releaseSend(SendReservation reservation, boolean accepted) {
        if (accepted) {
            return;
        }
        @SuppressWarnings("unchecked")
        List<String> windowKeys = (List<String>) reservation.handle();
        Long result = RedisFailures.call("sms-rate-limit-compensate", () -> template.execute(
                COMPENSATE_SCRIPT, windowKeys));
        requireCompensated(result);
    }

    @Override
    public boolean createChallenge(String challengeId, String phone, String code, Instant now, int ttlSeconds) {
        String key = keys.smsChallenge(challengeId);
        String digest = StateKeys.codeDigest(code, challengeId);
        String expiresAtMillis = String.valueOf(now.plusSeconds(ttlSeconds).toEpochMilli());
        Long result = RedisFailures.call("sms-create-challenge", () -> template.execute(
                CREATE_SCRIPT, List.of(key),
                digest, phone, expiresAtMillis, String.valueOf(ttlSeconds)));
        return createdFromScriptResult(result);
    }

    @Override
    public Optional<String> consumeChallenge(String challengeId, String code, Instant now, int maxAttempts) {
        String key = keys.smsChallenge(challengeId);
        String digest = code == null || code.isBlank()
                ? NO_MATCH_DIGEST
                : StateKeys.codeDigest(code, challengeId);
        String result = RedisFailures.call("sms-consume-challenge", () -> template.execute(
                CONSUME_SCRIPT, List.of(key),
                digest, String.valueOf(now.toEpochMilli()), String.valueOf(maxAttempts)));
        return consumedFromScriptResult(result);
    }

    // ---------- 脚本返回码校验（非预期返回一律 fail-closed，绝不表现为业务失败） ----------

    /**
     * 校验限流预留脚本的返回值：{@code 0}=已预留；{@code >0}=retry-after。null 或负数视为后端异常。
     */
    static long retryAfterFromScriptResult(Long result) {
        if (result == null || result < 0L) {
            throw scriptFailure("sms-rate-limit-reserve");
        }
        return result;
    }

    /** 校验补偿脚本返回值：契约是恒为 {@code 1}；null 或其它值视为后端异常。 */
    static void requireCompensated(Long result) {
        if (result == null || result != 1L) {
            throw scriptFailure("sms-rate-limit-compensate");
        }
    }

    /**
     * 校验创建脚本返回值：{@code 1}=已创建；{@code 0}=challengeId 已存在（碰撞，调用方重生成）。
     * null 或其它值视为后端异常（fail-closed），<b>绝不</b>当作成功。
     */
    static boolean createdFromScriptResult(Long result) {
        if (result == null) {
            throw scriptFailure("sms-create-challenge");
        }
        if (result == 1L) {
            return true;
        }
        if (result == 0L) {
            return false;
        }
        throw scriptFailure("sms-create-challenge");
    }

    /**
     * 校验核销脚本返回值：{@code "!"}=业务失败（空 Optional）；{@code "+"+phone}=成功。
     * null 或其它形状（既非 {@code !} 也非 {@code +} 前缀）视为后端异常 fail-closed，
     * <b>绝不</b>伪装成"验证码错误/无此挑战"（401）。
     */
    static Optional<String> consumedFromScriptResult(String result) {
        if (result == null) {
            throw scriptFailure("sms-consume-challenge");
        }
        if (CONSUME_FAILURE.equals(result)) {
            return Optional.empty();
        }
        if (result.startsWith(CONSUME_SUCCESS_PREFIX)
                && result.length() > CONSUME_SUCCESS_PREFIX.length()) {
            return Optional.of(result.substring(CONSUME_SUCCESS_PREFIX.length()));
        }
        throw scriptFailure("sms-consume-challenge");
    }

    /** fail-closed 的后端异常（503 DEPENDENCY_UNAVAILABLE）；消息只含操作名，不含键/手机号/验证码。 */
    private static ApiException scriptFailure(String operation) {
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "sms state store script returned an unexpected result (operation=" + operation
                        + "); the request was NOT processed");
    }

    /** 从 classpath 加载不可变脚本单例（Spring 的脚本执行器会自动 EVALSHA → EVAL 回退）。 */
    private static <T> DefaultRedisScript<T> script(String location, Class<T> resultType) {
        DefaultRedisScript<T> script = new DefaultRedisScript<>();
        script.setLocation(new ClassPathResource(location));
        script.setResultType(resultType);
        return script;
    }
}

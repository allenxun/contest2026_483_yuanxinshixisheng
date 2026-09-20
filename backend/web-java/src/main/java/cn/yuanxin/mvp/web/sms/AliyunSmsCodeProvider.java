package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * 阿里云短信 {@link SmsCodeProvider} 真实实现（{@code app.sms.provider=aliyun}）。
 *
 * <p><b>issue 流程</b>：先本地节流<b>原子预留</b> → 生成 6 位随机码 → 调 {@link SmsSendGateway} →
 * <b>仅当平台受理（{@code Code=OK}）才创建 challenge 并返回</b>；发送未被受理时原子回退节流名额。
 * 任何失败都不创建 challenge，也<b>绝不</b>回退到 doubles 或返回一个"有效"挑战。失败映射：</p>
 * <ul>
 *   <li>{@link FailureKind#THROTTLED} → 429 {@code RATE_LIMITED}（带 {@code Retry-After} 头）；</li>
 *   <li>{@link FailureKind#CONFIGURATION} → 503 {@code DEPENDENCY_UNAVAILABLE}（消息注明不可重试）；</li>
 *   <li>{@link FailureKind#DEPENDENCY} → 503 {@code DEPENDENCY_UNAVAILABLE}（可退避重试，但短信非幂等）。</li>
 * </ul>
 *
 * <p><b>verify</b>：不存在/已过期/已核销/超过最大尝试次数 ⇒ {@code Optional.empty()}；
 * 正确且未超限 ⇒ 一次性核销并返回手机号（与 doubles 的 f02 401 语义一致）。</p>
 *
 * <p><b>状态与并发（BLOCKER 3 / IMPORTANT 8）</b>：challenge 与节流状态委托给 {@link SmsStateStore}：
 * {@link InMemorySmsStateStore}（{@code app.state.provider=memory}；逐字保留条带锁 + 容量上限的
 * 进程内语义）或 {@link RedisSmsStateStore}（{@code =redis}；Lua 原子步，跨实例一致）。
 * 因此本类自身<b>无共享可变状态</b>；"预检 → 发送 → 记录"的串行化与容量有界性由所选存储负责。</p>
 *
 * <p><b>节流语义精化（有意，如实披露）</b>：跨实例无法用进程内锁把"预检 → 远端发送 → 记录受理"
 * 串行化，Redis 后端改为<b>原子预留 + 失败补偿</b>：预留保证并发下绝不超发，发送未被受理时回退；
 * 稳态计数仍等于受理成功的发送数，差别仅在"发送失败瞬间名额被短暂占用"，方向更严格。
 * 详见 {@code backend/handoffs/B-redis-state-migration.md} §4。</p>
 *
 * <p><b>风控</b>：验证码由 {@link SecureRandom} 生成 6 位（会避开通用测试码 {@code 123456}）；
 * TTL、单 challenge 尝试上限、以及三窗口节流（默认对齐官方：同手机号 1 分钟 1 条 / 1 小时
 * 5 条 / 1 天 10 条，按 <b>UTC+8 自然窗口</b>）均由 {@link SmsRiskProperties} 配置。时间源为
 * 可注入 {@link Clock}（测试用固定/可变时钟，不用 sleep）；窗口归一在
 * {@link SmsThrottleWindows}，两个后端共用。</p>
 *
 * <p><b>脱敏</b>：日志与异常消息绝不包含完整手机号、验证码、challengeId 原文或凭据；
 * 手机号一律经 {@link SmsMasking#maskPhone(String)}。</p>
 */
public class AliyunSmsCodeProvider implements SmsCodeProvider {

    /** 通用 dev/test 固定码；真实模式绝不使用它，避免"万能码"误解。 */
    static final String DEV_FIXED_CODE = "123456";

    private static final int CODE_BOUND = 1_000_000;

    /**
     * challengeId 碰撞时的有界重生成上限。challengeId 为 UUID + 随机长整数，正常碰撞率约为 0；
     * 连续 3 次仍碰撞说明存储/脚本异常，此时 fail-closed，<b>绝不</b>签发一个并未真正写入的 challenge。
     */
    static final int CHALLENGE_ID_MAX_ATTEMPTS = 3;

    private final SmsSendGateway gateway;
    private final SmsRiskProperties risk;
    private final Clock clock;
    private final SmsStateStore store;
    private final SecureRandom random = new SecureRandom();

    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk) {
        this(gateway, risk, Clock.systemUTC());
    }

    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk, Clock clock) {
        this(gateway, risk, clock, new InMemorySmsStateStore(risk));
    }

    /** 可配置容量上限的构造器（测试用；生产默认走注入 {@link SmsStateStore} 的构造器）。 */
    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk, Clock clock,
                                 int maxChallenges, int maxTrackedPhones) {
        this(gateway, risk, clock, new InMemorySmsStateStore(risk, maxChallenges, maxTrackedPhones));
    }

    /** 生产/装配构造器：存储后端由 {@code app.state.provider} 决定。 */
    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk, Clock clock,
                                 SmsStateStore store) {
        this.gateway = gateway;
        this.risk = risk;
        this.clock = clock;
        this.store = store;
    }

    @Override
    public ChallengeOutcome issue(String phone, String purpose) {
        Instant now = clock.instant();
        // 原子预留：同手机号的"预检 → 发送 → 记录"在内存后端由条带锁串行化；
        // Redis 后端由单个 Lua 保证并发下绝不超发（失败时回退，见 finally）。
        SmsStateStore.SendReservation reservation = store.reserveSend(phone, now);
        if (!reservation.granted()) {
            throw rateLimited(reservation.retryAfterSeconds());
        }
        boolean accepted = false;
        try {
            String code = randomCode();
            SendResult result;
            try {
                result = gateway.send(phone, code);
            } catch (RuntimeException unexpected) {
                // 缝实现异常一律视为依赖失败；绝不回退替身、绝不签发 challenge。
                throw dependencyUnavailable("send exception " + unexpected.getClass().getSimpleName(),
                        "retry with backoff; sms send is not idempotent");
            }
            if (!result.accepted()) {
                throw mapFailure(result);
            }
            // 只统计已受理发送；失败/被节流拒绝的请求绝不计入。
            accepted = true;
            store.commitSend(reservation, now);
            // 有界重生成 challengeId：只有真正写入（createChallenge 返回 true）才签发；
            // 连续碰撞达到上限则 fail-closed，绝不返回一个无法核销的 challengeId。
            String challengeId = null;
            for (int attempt = 0; attempt < CHALLENGE_ID_MAX_ATTEMPTS; attempt++) {
                String candidate = newChallengeId();
                if (store.createChallenge(candidate, phone, code, now, risk.challengeTtlSeconds())) {
                    challengeId = candidate;
                    break;
                }
            }
            if (challengeId == null) {
                throw dependencyUnavailable(
                        "challenge id collision persisted after " + CHALLENGE_ID_MAX_ATTEMPTS
                                + " attempts",
                        "retry the request; no challenge was issued");
            }
            return new ChallengeOutcome(challengeId, risk.retryAfterSeconds());
        } finally {
            store.releaseSend(reservation, accepted);
        }
    }

    @Override
    public Optional<String> verify(String challengeId, String code) {
        if (challengeId == null || challengeId.isBlank()) {
            return Optional.empty();
        }
        return store.consumeChallenge(challengeId, code, clock.instant(), risk.maxVerifyAttempts());
    }

    private ApiException mapFailure(SendResult result) {
        String code = result.code() == null ? "<none>" : result.code();
        return switch (result.failureKind()) {
            case THROTTLED -> rateLimited(risk.retryAfterSeconds());
            case CONFIGURATION -> dependencyUnavailable(
                    "aliyun rejected configuration (code=" + code + "; not retryable)",
                    "fix the signature/template/permission configuration");
            case DEPENDENCY -> dependencyUnavailable(
                    "aliyun dependency failure (code=" + code + ")",
                    "retry with backoff; sms send is not idempotent");
        };
    }

    private static ApiException rateLimited(long retryAfterSeconds) {
        long retryAfter = Math.max(1, retryAfterSeconds);
        return new ApiException(ErrorCode.RATE_LIMITED,
                ErrorCode.RATE_LIMITED.defaultStatus().value(),
                "sms send throttled by local pre-check; retry after Retry-After seconds",
                Map.of("retryAfterSeconds", retryAfter),
                Map.of("Retry-After", String.valueOf(retryAfter)));
    }

    private static ApiException dependencyUnavailable(String detail, String guidance) {
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "sms provider unavailable: " + detail + "; " + guidance);
    }

    private String randomCode() {
        String code;
        do {
            code = String.format("%06d", random.nextInt(CODE_BOUND));
        } while (DEV_FIXED_CODE.equals(code));
        return code;
    }

    private String newChallengeId() {
        return UUID.randomUUID().toString().replace("-", "")
                + Long.toHexString(random.nextLong());
    }
}

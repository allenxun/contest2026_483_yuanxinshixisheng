package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 阿里云短信 {@link SmsCodeProvider} 真实实现（{@code app.sms.provider=aliyun}）。
 *
 * <p><b>issue 流程</b>：先本地节流预检 → 生成 6 位随机码 → 调 {@link SmsSendGateway} →
 * <b>仅当平台受理（{@code Code=OK}）才在内存创建 challenge 并返回</b>。任何失败都不创建
 * challenge，也<b>绝不</b>回退到 doubles 或返回一个"有效"挑战。失败映射：</p>
 * <ul>
 *   <li>{@link FailureKind#THROTTLED} → 429 {@code RATE_LIMITED}（带 {@code Retry-After} 头）；</li>
 *   <li>{@link FailureKind#CONFIGURATION} → 503 {@code DEPENDENCY_UNAVAILABLE}（消息注明不可重试）；</li>
 *   <li>{@link FailureKind#DEPENDENCY} → 503 {@code DEPENDENCY_UNAVAILABLE}（可退避重试，但短信非幂等）。</li>
 * </ul>
 *
 * <p><b>verify</b>：不存在/已过期/已核销/超过最大尝试次数 ⇒ {@code Optional.empty()}；
 * 正确且未超限 ⇒ 一次性核销并返回手机号（与 doubles 的 f02 401 语义一致）。</p>
 *
 * <p><b>风控</b>：验证码由 {@link SecureRandom} 生成 6 位（会避开通用测试码 {@code 123456}）；
 * TTL、单 challenge 尝试上限、以及三窗口节流（默认对齐官方：同手机号 1 分钟 1 条 / 1 小时
 * 5 条 / 1 天 10 条，按 <b>UTC+8 自然窗口</b>）均由 {@link SmsRiskProperties} 配置。时间源为
 * 可注入 {@link Clock}（测试用固定/可变时钟，不用 sleep）。</p>
 *
 * <p><b>已知局限（如实披露）</b>：challenge 与节流历史均为<b>进程内内存</b>
 * （{@code ConcurrentHashMap}）⇒ 应用重启即失效、多实例之间不共享。本地节流仅是<b>调用计费
 * 接口前的预检</b>，平台仍可能返回 {@code isv.BUSINESS_LIMIT_CONTROL} 等平台流控。</p>
 */
public class AliyunSmsCodeProvider implements SmsCodeProvider {

    /** 官方短信验证码频控窗口按 UTC+8 自然分钟/小时/日。 */
    static final ZoneOffset CN_OFFSET = ZoneOffset.ofHours(8);

    /** 通用 dev/test 固定码；真实模式绝不使用它，避免"万能码"误解。 */
    static final String DEV_FIXED_CODE = "123456";

    private static final int CODE_BOUND = 1_000_000;

    private final SmsSendGateway gateway;
    private final SmsRiskProperties risk;
    private final Clock clock;
    private final SecureRandom random = new SecureRandom();
    private final Map<String, Challenge> challenges = new ConcurrentHashMap<>();
    private final Map<String, Deque<Instant>> acceptedSends = new ConcurrentHashMap<>();

    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk) {
        this(gateway, risk, Clock.systemUTC());
    }

    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk, Clock clock) {
        this.gateway = gateway;
        this.risk = risk;
        this.clock = clock;
    }

    @Override
    public ChallengeOutcome issue(String phone, String purpose) {
        Instant now = clock.instant();

        long throttleRetryAfter = throttleRetryAfterSeconds(phone, now);
        if (throttleRetryAfter > 0) {
            throw rateLimited(throttleRetryAfter);
        }

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

        recordAcceptedSend(phone, now);
        String challengeId = newChallengeId();
        challenges.put(challengeId,
                new Challenge(phone, code, now.plusSeconds(risk.challengeTtlSeconds())));
        return new ChallengeOutcome(challengeId, risk.retryAfterSeconds());
    }

    @Override
    public Optional<String> verify(String challengeId, String code) {
        Challenge challenge = challenges.get(challengeId);
        if (challenge == null) {
            return Optional.empty();
        }
        synchronized (challenge) {
            if (challenge.consumed) {
                return Optional.empty();
            }
            if (clock.instant().isAfter(challenge.expiresAt)) {
                challenges.remove(challengeId, challenge);
                return Optional.empty();
            }
            if (challenge.attempts.get() >= risk.maxVerifyAttempts()) {
                return Optional.empty();
            }
            boolean matches = code != null && MessageDigest.isEqual(
                    challenge.code.getBytes(StandardCharsets.UTF_8),
                    code.getBytes(StandardCharsets.UTF_8));
            if (!matches) {
                challenge.attempts.incrementAndGet();
                return Optional.empty();
            }
            challenge.consumed = true;
            challenges.remove(challengeId, challenge);
            return Optional.of(challenge.phone);
        }
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

    private long throttleRetryAfterSeconds(String phone, Instant now) {
        Deque<Instant> history = acceptedSends.get(phone);
        if (history == null) {
            return 0;
        }
        ZonedDateTime nowCn = now.atZone(CN_OFFSET);
        long retryAfter = 0;
        synchronized (history) {
            long inMinute = history.stream().filter(t -> sameMinute(t, nowCn)).count();
            long inHour = history.stream().filter(t -> sameHour(t, nowCn)).count();
            long inDay = history.stream().filter(t -> sameDay(t, nowCn)).count();
            if (inMinute >= risk.maxPerMinute()) {
                retryAfter = Math.max(retryAfter, secondsToNextMinute(nowCn));
            }
            if (inHour >= risk.maxPerHour()) {
                retryAfter = Math.max(retryAfter, secondsToNextHour(nowCn));
            }
            if (inDay >= risk.maxPerDay()) {
                retryAfter = Math.max(retryAfter, secondsToNextDay(nowCn));
            }
        }
        return retryAfter;
    }

    private void recordAcceptedSend(String phone, Instant at) {
        Deque<Instant> history = acceptedSends.computeIfAbsent(phone, ignored -> new ArrayDeque<>());
        synchronized (history) {
            history.addLast(at);
            Instant cutoff = at.minus(Duration.ofDays(2));
            while (!history.isEmpty() && history.peekFirst().isBefore(cutoff)) {
                history.pollFirst();
            }
        }
    }

    private static boolean sameMinute(Instant instant, ZonedDateTime nowCn) {
        return instant.atZone(CN_OFFSET).truncatedTo(ChronoUnit.MINUTES)
                .equals(nowCn.truncatedTo(ChronoUnit.MINUTES));
    }

    private static boolean sameHour(Instant instant, ZonedDateTime nowCn) {
        return instant.atZone(CN_OFFSET).truncatedTo(ChronoUnit.HOURS)
                .equals(nowCn.truncatedTo(ChronoUnit.HOURS));
    }

    private static boolean sameDay(Instant instant, ZonedDateTime nowCn) {
        return instant.atZone(CN_OFFSET).toLocalDate().equals(nowCn.toLocalDate());
    }

    private static long secondsToNextMinute(ZonedDateTime nowCn) {
        return Math.max(1, 60L - nowCn.getSecond());
    }

    private static long secondsToNextHour(ZonedDateTime nowCn) {
        long elapsed = nowCn.getMinute() * 60L + nowCn.getSecond();
        return Math.max(1, 3600L - elapsed);
    }

    private static long secondsToNextDay(ZonedDateTime nowCn) {
        ZonedDateTime nextDay = nowCn.toLocalDate().plusDays(1).atStartOfDay(CN_OFFSET);
        return Math.max(1, Duration.between(nowCn, nextDay).getSeconds());
    }

    /** 进程内 challenge（一次性、带尝试上限）。 */
    private static final class Challenge {
        private final String phone;
        private final String code;
        private final Instant expiresAt;
        private final AtomicInteger attempts = new AtomicInteger();
        private volatile boolean consumed;

        private Challenge(String phone, String code, Instant expiresAt) {
            this.phone = phone;
            this.code = code;
            this.expiresAt = expiresAt;
        }
    }
}

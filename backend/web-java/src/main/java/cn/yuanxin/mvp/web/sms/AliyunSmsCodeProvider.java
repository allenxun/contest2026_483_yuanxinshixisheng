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
import java.util.concurrent.locks.ReentrantLock;

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
 * <p><b>并发安全（BLOCKER 3）</b>：{@code issue} 的「预检 → 远端发送 → 记录受理」三步在
 * <b>按手机号分条带的固定数量 {@link ReentrantLock}</b> 内整体串行化（条带数 {@link #SEND_STRIPES}，
 * 索引 {@code Math.floorMod(phone.hashCode(), SEND_STRIPES)}）。同手机号必须串行，才能防止
 * 并发请求全部通过预检后各发一条<b>计费</b>短信；不同手机号落在不同条带，基本并行。
 * <b>刻意</b>把远端发送包含在锁内（牺牲同号吞吐换取计费安全）。不用无界 per-phone 锁 map，
 * 避免锁对象永不回收的泄漏。</p>
 *
 * <p><b>有界内存（IMPORTANT 8）</b>：两个内存 map 均有上限并做机会式清理：</p>
 * <ul>
 *   <li>{@code challenges}：每次 {@code issue}/{@code verify} 清理已过期条目；超过
 *       {@code maxChallenges} 时<b>拒绝新签发</b>并抛 503 {@code DEPENDENCY_UNAVAILABLE}
 *       （消息只含上限值、<b>绝不</b>含手机号）——不静默丢弃最旧的有效 challenge 导致用户无法登录；
 *       尝试次数耗尽即刻 remove。</li>
 *   <li>{@code acceptedSends}：按手机号剪枝超过保留窗口的历史，历史为空即移除该 key；
 *       phone key 数量超过 {@code maxTrackedPhones} 时同样拒绝新签发（fail-closed）。</li>
 * </ul>
 * <p>容量上限通过构造器注入（默认 {@link #DEFAULT_MAX_CHALLENGES}/{@link #DEFAULT_MAX_TRACKED_PHONES}），
 * 但<b>不改变</b>任何既有风控语义（TTL、一次性、尝试上限、三窗口 UTC+8 自然窗口）。</p>
 *
 * <p><b>已知局限（如实披露）</b>：challenge 与节流历史均为<b>进程内内存</b>
 * （{@code ConcurrentHashMap}）⇒ 应用重启即失效、多实例之间不共享。本地节流仅是<b>调用计费
 * 接口前的预检</b>，平台仍可能返回 {@code isv.BUSINESS_LIMIT_CONTROL} 等平台流控。
 * 容量上限在跨条带并发下允许<b>有界</b>瞬时超出（最多为并发进行中的签发数）。</p>
 */
public class AliyunSmsCodeProvider implements SmsCodeProvider {

    /** 官方短信验证码频控窗口按 UTC+8 自然分钟/小时/日。 */
    static final ZoneOffset CN_OFFSET = ZoneOffset.ofHours(8);

    /** 通用 dev/test 固定码；真实模式绝不使用它，避免"万能码"误解。 */
    static final String DEV_FIXED_CODE = "123456";

    private static final int CODE_BOUND = 1_000_000;

    /** 按手机号分条带的固定锁数量；不同条带基本并行，同条带串行。 */
    static final int SEND_STRIPES = 64;

    /** 未核销 challenge 的默认容量上限；超限拒绝新签发（fail-closed），不丢有效 challenge。 */
    static final int DEFAULT_MAX_CHALLENGES = 10_000;

    /** 节流历史中 phone key 的默认数量上限；超限拒绝新签发（fail-closed）。 */
    static final int DEFAULT_MAX_TRACKED_PHONES = 10_000;

    /** 节流历史的保留窗口；超出即剪枝，用于回收 phone key。 */
    static final Duration ACCEPTED_SEND_RETENTION = Duration.ofDays(2);

    private final SmsSendGateway gateway;
    private final SmsRiskProperties risk;
    private final Clock clock;
    private final SecureRandom random = new SecureRandom();
    private final Map<String, Challenge> challenges = new ConcurrentHashMap<>();
    private final Map<String, Deque<Instant>> acceptedSends = new ConcurrentHashMap<>();
    private final ReentrantLock[] sendStripes = new ReentrantLock[SEND_STRIPES];
    private final int maxChallenges;
    private final int maxTrackedPhones;
    private final Object capacityMonitor = new Object();
    private int reservedChallenges;

    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk) {
        this(gateway, risk, Clock.systemUTC());
    }

    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk, Clock clock) {
        this(gateway, risk, clock, DEFAULT_MAX_CHALLENGES, DEFAULT_MAX_TRACKED_PHONES);
    }

    /** 可配置容量上限的构造器（测试用；生产默认走 3 参构造器）。 */
    public AliyunSmsCodeProvider(SmsSendGateway gateway, SmsRiskProperties risk, Clock clock,
                                 int maxChallenges, int maxTrackedPhones) {
        if (maxChallenges <= 0 || maxTrackedPhones <= 0) {
            throw new IllegalArgumentException("capacity limits must be positive");
        }
        this.gateway = gateway;
        this.risk = risk;
        this.clock = clock;
        this.maxChallenges = maxChallenges;
        this.maxTrackedPhones = maxTrackedPhones;
        for (int i = 0; i < SEND_STRIPES; i++) {
            sendStripes[i] = new ReentrantLock();
        }
    }

    @Override
    public ChallengeOutcome issue(String phone, String purpose) {
        // BLOCKER 3：预检 → 发送 → 记录必须在同一把按手机号分条带的锁内完成，
        // 否则并发请求会全部通过预检、各发一条计费短信。
        ReentrantLock stripe = sendStripes[Math.floorMod(phone.hashCode(), SEND_STRIPES)];
        stripe.lock();
        try {
            Instant now = clock.instant();

            long throttleRetryAfter = throttleRetryAfterSeconds(phone, now);
            if (throttleRetryAfter > 0) {
                throw rateLimited(throttleRetryAfter);
            }

            // IMPORTANT 8：有界内存检查在发送之前完成，避免"已计费发送后才因容量拒绝"。
            ensureTrackedPhoneCapacity(phone, now);
            reserveChallengeSlot(now);
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
                recordAcceptedSend(phone, now);
                String challengeId = newChallengeId();
                challenges.put(challengeId,
                        new Challenge(phone, code, now.plusSeconds(risk.challengeTtlSeconds())));
                return new ChallengeOutcome(challengeId, risk.retryAfterSeconds());
            } finally {
                releaseChallengeReservation();
            }
        } finally {
            stripe.unlock();
        }
    }

    @Override
    public Optional<String> verify(String challengeId, String code) {
        // IMPORTANT 8：机会式清理已过期条目，避免过期未核销的 challenge 永不回收。
        pruneExpiredChallenges(clock.instant());
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
                // 尝试次数已耗尽：立即回收，不再占用内存。
                challenges.remove(challengeId, challenge);
                return Optional.empty();
            }
            boolean matches = code != null && MessageDigest.isEqual(
                    challenge.code.getBytes(StandardCharsets.UTF_8),
                    code.getBytes(StandardCharsets.UTF_8));
            if (!matches) {
                if (challenge.attempts.incrementAndGet() >= risk.maxVerifyAttempts()) {
                    // 本次错误尝试后达到上限：立即回收。
                    challenges.remove(challengeId, challenge);
                }
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

    /** 移除已过期 challenge（机会式，O(n)，n 受 {@code maxChallenges} 约束）。 */
    private void pruneExpiredChallenges(Instant now) {
        challenges.entrySet().removeIf(entry -> now.isAfter(entry.getValue().expiresAt));
    }

    /**
     * 在发送前<b>预留</b>一个 challenge 名额：先清理过期，仍超上限则拒绝新签发。
     * 预留计数保证跨条带并发下容量不被突破；无论发送成败，最终都须
     * {@link #releaseChallengeReservation() 释放预留}（成功时名额转为已存 challenge）。
     */
    private void reserveChallengeSlot(Instant now) {
        synchronized (capacityMonitor) {
            pruneExpiredChallenges(now);
            if (challenges.size() + reservedChallenges >= maxChallenges) {
                throw dependencyUnavailable(
                        "local sms challenge capacity reached (max=" + maxChallenges + "); retry later",
                        "capacity guard prevents unbounded memory; no valid challenge was dropped");
            }
            reservedChallenges++;
        }
    }

    private void releaseChallengeReservation() {
        synchronized (capacityMonitor) {
            reservedChallenges--;
        }
    }

    /**
     * 发送前检查该手机号的节流历史 key 是否可容纳：先机会式剪枝并回收历史为空的 key，
     * 仍达上限则拒绝新签发（fail-closed；绝不静默丢弃既有节流历史，否则会放宽风控）。
     */
    private void ensureTrackedPhoneCapacity(String phone, Instant now) {
        if (acceptedSends.containsKey(phone)) {
            return;
        }
        pruneStaleAcceptedSends(now);
        if (acceptedSends.size() >= maxTrackedPhones) {
            throw dependencyUnavailable(
                    "local sms tracking capacity reached (max=" + maxTrackedPhones + "); retry later",
                    "fail-closed to preserve throttle integrity; retry later");
        }
    }

    /**
     * 机会式剪枝：移除超过保留窗口的历史；某 phone 的历史为空则移除该 key。
     * 用 {@code computeIfPresent} 与 {@link #recordAcceptedSend} 的 {@code compute} 互斥，
     * 避免与并发记录竞争导致历史丢失。
     */
    private void pruneStaleAcceptedSends(Instant now) {
        Instant cutoff = now.minus(ACCEPTED_SEND_RETENTION);
        for (String phone : acceptedSends.keySet()) {
            acceptedSends.computeIfPresent(phone, (key, history) -> {
                synchronized (history) {
                    while (!history.isEmpty() && history.peekFirst().isBefore(cutoff)) {
                        history.pollFirst();
                    }
                }
                return history.isEmpty() ? null : history;
            });
        }
    }

    private void recordAcceptedSend(String phone, Instant at) {
        Instant cutoff = at.minus(ACCEPTED_SEND_RETENTION);
        acceptedSends.compute(phone, (key, existing) -> {
            Deque<Instant> history = existing == null ? new ArrayDeque<>() : existing;
            synchronized (history) {
                history.addLast(at);
                while (!history.isEmpty() && history.peekFirst().isBefore(cutoff)) {
                    history.pollFirst();
                }
            }
            return history;
        });
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

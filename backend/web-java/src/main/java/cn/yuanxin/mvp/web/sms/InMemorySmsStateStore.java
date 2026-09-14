package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;

import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;

/**
 * 进程内短信状态存储（{@code app.state.provider=memory}，默认；仅供隔离测试与 doubles）。
 *
 * <p><b>逐字保留迁移前的内存语义</b>（从 {@code AliyunSmsCodeProvider} 原样搬入，仅反射可观测面
 * 改为指向本类）：{@code maxChallenges}/{@code maxTrackedPhones} 容量上限、机会式回收
 * {@code pruneExpiredChallenges}/{@code pruneStaleAcceptedSends}、以及
 * {@code ReentrantLock[64]} 条带锁保护的"预检 → 远端发送 → 记录"临界区。</p>
 *
 * <p><b>条带锁</b>：{@link #reserveSend} 取得该手机号条带锁并一直持有到
 * {@link #releaseSend}；因此同一手机号的"预检 → 远端发送 → 记录受理"整体串行，
 * 并发请求不会全部通过预检后各发一条<b>计费</b>短信。跨实例下该锁无效——那正是
 * {@link RedisSmsStateStore} 使用原子预留 + 失败补偿的原因。</p>
 *
 * <p><b>已知局限（如实披露）</b>：状态为进程内 {@code ConcurrentHashMap} ⇒ 应用重启即失效、
 * 多实例不共享。生产必须用 Redis（{@code StateStoreConfigGuard} 在生产 + real 下拒绝 memory）。</p>
 */
public final class InMemorySmsStateStore implements SmsStateStore {

    /** 按手机号分条带的固定锁数量；不同条带基本并行，同条带串行。 */
    static final int SEND_STRIPES = 64;

    /** 未核销 challenge 的默认容量上限；超限拒绝新签发（fail-closed），不丢有效 challenge。 */
    public static final int DEFAULT_MAX_CHALLENGES = 10_000;

    /** 节流历史中 phone key 的默认数量上限；超限拒绝新签发（fail-closed）。 */
    public static final int DEFAULT_MAX_TRACKED_PHONES = 10_000;

    /** 节流历史的保留窗口；超出即剪枝，用于回收 phone key。 */
    static final Duration ACCEPTED_SEND_RETENTION = Duration.ofDays(2);

    private final SmsRiskProperties risk;
    private final Map<String, Challenge> challenges = new ConcurrentHashMap<>();
    private final Map<String, Deque<Instant>> acceptedSends = new ConcurrentHashMap<>();
    private final ReentrantLock[] sendStripes = new ReentrantLock[SEND_STRIPES];
    private final int maxChallenges;
    private final int maxTrackedPhones;
    private final Object capacityMonitor = new Object();
    private int reservedChallenges;

    public InMemorySmsStateStore(SmsRiskProperties risk) {
        this(risk, DEFAULT_MAX_CHALLENGES, DEFAULT_MAX_TRACKED_PHONES);
    }

    public InMemorySmsStateStore(SmsRiskProperties risk, int maxChallenges, int maxTrackedPhones) {
        if (maxChallenges <= 0 || maxTrackedPhones <= 0) {
            throw new IllegalArgumentException("capacity limits must be positive");
        }
        this.risk = risk;
        this.maxChallenges = maxChallenges;
        this.maxTrackedPhones = maxTrackedPhones;
        for (int i = 0; i < SEND_STRIPES; i++) {
            sendStripes[i] = new ReentrantLock();
        }
    }

    @Override
    public SendReservation reserveSend(String phone, Instant now) {
        ReentrantLock stripe = stripeFor(phone);
        stripe.lock();
        try {
            long throttleRetryAfter = throttleRetryAfterSeconds(phone, now);
            if (throttleRetryAfter > 0) {
                stripe.unlock();
                return SendReservation.throttled(throttleRetryAfter);
            }
            // 有界内存检查在发送之前完成，避免"已计费发送后才因容量拒绝"。
            ensureTrackedPhoneCapacity(phone, now);
            reserveChallengeSlot(now);
            return SendReservation.granted(phone, stripe);
        } catch (RuntimeException ex) {
            stripe.unlock();
            throw ex;
        }
    }

    @Override
    public void commitSend(SendReservation reservation, Instant now) {
        // 只统计已受理发送；失败/被节流拒绝的请求绝不计入。
        recordAcceptedSend(reservation.phone(), now);
    }

    @Override
    public void releaseSend(SendReservation reservation, boolean accepted) {
        releaseChallengeReservation();
        stripeFor(reservation.phone()).unlock();
    }

    @Override
    public boolean createChallenge(String challengeId, String phone, String code, Instant now, int ttlSeconds) {
        // 容量名额已在 reserveSend 预留；发送成功即转为已存 challenge。
        // putIfAbsent 与 Redis 的 SET NX 等价：返回 false 表示 challengeId 碰撞，调用方须重生成。
        return challenges.putIfAbsent(challengeId,
                new Challenge(phone, code, now.plusSeconds(ttlSeconds))) == null;
    }

    @Override
    public Optional<String> consumeChallenge(String challengeId, String code, Instant now, int maxAttempts) {
        // 机会式清理已过期条目，避免过期未核销的 challenge 永不回收。
        pruneExpiredChallenges(now);
        Challenge challenge = challenges.get(challengeId);
        if (challenge == null) {
            return Optional.empty();
        }
        synchronized (challenge) {
            if (challenge.consumed) {
                return Optional.empty();
            }
            if (now.isAfter(challenge.expiresAt)) {
                challenges.remove(challengeId, challenge);
                return Optional.empty();
            }
            if (challenge.attempts.get() >= maxAttempts) {
                // 尝试次数已耗尽：立即回收，不再占用内存。
                challenges.remove(challengeId, challenge);
                return Optional.empty();
            }
            boolean matches = code != null && java.security.MessageDigest.isEqual(
                    challenge.code.getBytes(java.nio.charset.StandardCharsets.UTF_8),
                    code.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            if (!matches) {
                if (challenge.attempts.incrementAndGet() >= maxAttempts) {
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

    private ReentrantLock stripeFor(String phone) {
        return sendStripes[Math.floorMod(phone.hashCode(), SEND_STRIPES)];
    }

    private long throttleRetryAfterSeconds(String phone, Instant now) {
        Deque<Instant> history = acceptedSends.get(phone);
        if (history == null) {
            return 0;
        }
        ZonedDateTime nowCn = now.atZone(SmsThrottleWindows.CN_OFFSET);
        long retryAfter = 0;
        synchronized (history) {
            long inMinute = history.stream()
                    .filter(t -> SmsThrottleWindows.sameMinute(t, nowCn)).count();
            long inHour = history.stream()
                    .filter(t -> SmsThrottleWindows.sameHour(t, nowCn)).count();
            long inDay = history.stream()
                    .filter(t -> SmsThrottleWindows.sameDay(t, nowCn)).count();
            if (inMinute >= risk.maxPerMinute()) {
                retryAfter = Math.max(retryAfter, SmsThrottleWindows.secondsToNextMinute(nowCn));
            }
            if (inHour >= risk.maxPerHour()) {
                retryAfter = Math.max(retryAfter, SmsThrottleWindows.secondsToNextHour(nowCn));
            }
            if (inDay >= risk.maxPerDay()) {
                retryAfter = Math.max(retryAfter, SmsThrottleWindows.secondsToNextDay(nowCn));
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
     * {@link #releaseSend} 释放预留（成功时名额转为已存 challenge）。
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

    private static ApiException dependencyUnavailable(String detail, String guidance) {
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "sms provider unavailable: " + detail + "; " + guidance);
    }

    // ---------- 等价的测试可观测面（替代对 provider 私有 map 的反射） ----------

    /** 未核销 challenge 的只读视图（供测试断言"机会式回收 / 容量 / 一次性"等价语义）。 */
    Map<String, ?> challengeView() {
        return challenges;
    }

    /** 已受理发送历史 key 的只读视图（供测试断言保留窗口剪枝与 phone key 容量）。 */
    Map<String, ?> acceptedSendsView() {
        return acceptedSends;
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

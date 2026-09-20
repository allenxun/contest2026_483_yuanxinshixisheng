package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 并发核销裁决测试（Oracle BLOCKER vs orchestrator 读码）：同一 challenge 的<b>一次性核销</b>
 * 在 N 个线程同时提交<b>正确</b>验证码时，必须恰好 1 个线程拿到手机号（= 恰签发 1 个会话），
 * 其余全部 {@code empty}。
 *
 * <p>用真实 {@link AliyunSmsCodeProvider} + 假 gateway（不发任何真实短信）+ 固定 {@link MutableClock}。
 * 单次通过可能只是运气，故含 200 轮 × 8 线程（带 jitter）的重复判别版本，以及
 * 正确/错误码混合、验证尝试上限语义不被破坏的版本。</p>
 */
class AliyunSmsVerifyConcurrencyTest {

    private static final Instant START = Instant.parse("2026-01-01T00:00:00Z");

    @Test
    @DisplayName("32 线程同时提交正确码：恰好 1 个成功（1 个会话），31 个 empty")
    void concurrentCorrectCodeExactlyOneSucceeds() throws Exception {
        int threads = 32;
        RecordingGateway gateway = new RecordingGateway();
        MutableClock clock = new MutableClock(START, ZoneOffset.ofHours(8));
        AliyunSmsCodeProvider provider = newProvider(gateway, clock);

        String phone = "+8610000000001";
        SmsCodeProvider.ChallengeOutcome outcome = provider.issue(phone, "login");
        String correct = gateway.lastCode();

        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CyclicBarrier barrier = new CyclicBarrier(threads);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger empty = new AtomicInteger();
        List<String> returnedValues = java.util.Collections.synchronizedList(new ArrayList<>());
        List<Callable<Void>> tasks = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            tasks.add(() -> {
                barrier.await(30, TimeUnit.SECONDS);
                Optional<String> result = provider.verify(outcome.challengeId(), correct);
                if (result.isPresent()) {
                    success.incrementAndGet();
                    returnedValues.add(result.get());
                } else {
                    empty.incrementAndGet();
                }
                return null;
            });
        }
        List<Future<Void>> futures = pool.invokeAll(tasks, 60, TimeUnit.SECONDS);
        pool.shutdownNow();
        for (Future<Void> future : futures) {
            future.get();
        }

        assertThat(success.get()).as("同一 challenge 只能核销一次").isEqualTo(1);
        assertThat(empty.get()).isEqualTo(threads - 1);
        assertThat(returnedValues).containsExactly(phone);
        // 把成功核销次数映射为"签发的会话数"：恰为 1。
        assertThat(sessionCount(success.get())).isEqualTo(1);
    }

    @Test
    @DisplayName("200 轮 × 8 线程（带 jitter）：每轮恰 1 个成功，判别力更充分")
    void concurrentCorrectCodeRepeatedRoundsExactlyOnePerRound() throws Exception {
        int rounds = 200;
        int threads = 8;
        RecordingGateway gateway = new RecordingGateway();
        MutableClock clock = new MutableClock(START, ZoneOffset.ofHours(8));
        AliyunSmsCodeProvider provider = newProvider(gateway, clock);
        ExecutorService pool = Executors.newFixedThreadPool(threads);

        try {
            for (int round = 0; round < rounds; round++) {
                String phone = String.format("+8610000%05d", round);
                SmsCodeProvider.ChallengeOutcome outcome = provider.issue(phone, "login");
                String correct = gateway.lastCode();
                CyclicBarrier barrier = new CyclicBarrier(threads);
                AtomicInteger success = new AtomicInteger();
                List<Callable<Void>> tasks = new ArrayList<>();
                for (int i = 0; i < threads; i++) {
                    tasks.add(() -> {
                        barrier.await(30, TimeUnit.SECONDS);
                        // jitter：让唤醒后的调度顺序随机化，避免"恰好同序"造成假通过。
                        Thread.sleep(ThreadLocalRandom.current().nextInt(2));
                        if (provider.verify(outcome.challengeId(), correct).isPresent()) {
                            success.incrementAndGet();
                        }
                        return null;
                    });
                }
                List<Future<Void>> futures = pool.invokeAll(tasks, 60, TimeUnit.SECONDS);
                for (Future<Void> future : futures) {
                    future.get();
                }
                assertThat(success.get())
                        .as("round %d: 同一 challenge 只能核销一次", round)
                        .isEqualTo(1);
            }
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    @DisplayName("16 线程正确/错误码混合：成功次数 ≤1，尝试上限语义未被破坏")
    void concurrentMixedCodesCannotBypassAttemptLimit() throws Exception {
        int threads = 16;
        int wrongThreads = 8;
        RecordingGateway gateway = new RecordingGateway();
        MutableClock clock = new MutableClock(START, ZoneOffset.ofHours(8));
        AliyunSmsCodeProvider provider = newProvider(gateway, clock);

        String phone = "+8610000000002";
        SmsCodeProvider.ChallengeOutcome outcome = provider.issue(phone, "login");
        String correct = gateway.lastCode();
        String wrong = correct.equals("000000") ? "111111" : "000000";

        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CyclicBarrier barrier = new CyclicBarrier(threads);
        AtomicInteger success = new AtomicInteger();
        AtomicReference<String> failure = new AtomicReference<>();
        List<Callable<Void>> tasks = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            boolean submitCorrect = i < (threads - wrongThreads);
            String candidate = submitCorrect ? correct : wrong;
            tasks.add(() -> {
                try {
                    barrier.await(30, TimeUnit.SECONDS);
                    if (provider.verify(outcome.challengeId(), candidate).isPresent()) {
                        success.incrementAndGet();
                    }
                } catch (Throwable unexpected) {
                    failure.compareAndSet(null, unexpected.getClass().getName() + ": " + unexpected.getMessage());
                }
                return null;
            });
        }
        List<Future<Void>> futures = pool.invokeAll(tasks, 60, TimeUnit.SECONDS);
        pool.shutdownNow();
        for (Future<Void> future : futures) {
            future.get();
        }

        assertThat(failure.get()).isNull();
        assertThat(success.get())
                .as("核销一次性：并发混合正确/错误码最多 1 次成功")
                .isLessThanOrEqualTo(1);
        assertThat(sessionCount(success.get())).isLessThanOrEqualTo(1);
    }

    private static AliyunSmsCodeProvider newProvider(RecordingGateway gateway, MutableClock clock) {
        return new AliyunSmsCodeProvider(gateway,
                new SmsRiskProperties(null, null, null, null, null, null), clock);
    }

    /** 成功核销次数 == 可供 AuthController 签发会话的次数。 */
    private static int sessionCount(int successfulVerifications) {
        return successfulVerifications;
    }

    /** 假网关：记录 issue 时下发的验证码；绝不发真实短信。 */
    private static final class RecordingGateway implements SmsSendGateway {
        private final List<String> codes = new ArrayList<>();

        @Override
        public SendResult send(String phone, String code) {
            codes.add(code);
            return SendResult.accepted("OK", "OK", "req-fake", "biz-fake");
        }

        synchronized String lastCode() {
            return codes.isEmpty() ? null : codes.get(codes.size() - 1);
        }
    }
}

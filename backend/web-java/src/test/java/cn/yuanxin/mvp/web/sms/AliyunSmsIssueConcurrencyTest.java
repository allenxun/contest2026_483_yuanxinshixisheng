package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * BLOCKER 3 并发判别测试：同一手机号的本地节流预检 → 发送 → 记录必须是原子的，
 * 否则 N 个并发请求会全部通过预检、各发一条<b>计费</b>短信，突破「1 分钟 1 条」。
 *
 * <p>用固定时钟（同窗口）+ 假 gateway（发送前 sleep 拉大竞态窗口），只发内存请求、
 * <b>绝不</b>发真实短信。gateway 调用次数即计费发送次数。</p>
 */
class AliyunSmsIssueConcurrencyTest {

    private static final String FAKE_PHONE = "+8610000000000";

    @Test
    @DisplayName("16 线程同手机号并发 issue：恰好 1 次 gateway.send，其余全部 429 RATE_LIMITED")
    void concurrentSamePhoneIssuesOnlyOneBilledSend() throws Exception {
        int threads = 16;
        MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.ofHours(8));
        BlockingCountingGateway gateway = new BlockingCountingGateway(50);
        AliyunSmsCodeProvider provider = new AliyunSmsCodeProvider(gateway,
                new SmsRiskProperties(null, null, null, null, null, null), clock);

        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger accepted = new AtomicInteger();
        AtomicInteger rateLimited = new AtomicInteger();
        List<Long> retryAfterValues = new CopyOnWriteArrayList<>();
        List<Throwable> unexpected = new CopyOnWriteArrayList<>();

        for (int i = 0; i < threads; i++) {
            pool.submit(() -> {
                try {
                    startGate.await();
                    provider.issue(FAKE_PHONE, "login");
                    accepted.incrementAndGet();
                } catch (ApiException expected) {
                    if (expected.getCode() == ErrorCode.RATE_LIMITED) {
                        rateLimited.incrementAndGet();
                        Object retryAfter = expected.getDetails() == null
                                ? null : expected.getDetails().get("retryAfterSeconds");
                        if (retryAfter instanceof Long value) {
                            retryAfterValues.add(value);
                        }
                    } else {
                        unexpected.add(expected);
                    }
                } catch (Throwable unexpectedFailure) {
                    unexpected.add(unexpectedFailure);
                } finally {
                    done.countDown();
                }
            });
        }
        startGate.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        assertThat(finished).as("all issue() calls completed").isTrue();
        assertThat(unexpected).isEmpty();
        assertThat(gateway.sendCalls())
                .as("1 分钟窗口内对同一手机号的计费发送次数必须恰好为 1")
                .isEqualTo(1);
        assertThat(accepted).hasValue(1);
        assertThat(rateLimited).hasValue(threads - 1);
        assertThat(retryAfterValues).hasSize(threads - 1);
        assertThat(retryAfterValues).allSatisfy(value -> assertThat(value).isBetween(1L, 60L));
    }

    /** 假网关：计数 + 可配置 sleep 拉大并发竞态窗口。绝不发真实短信。 */
    private static final class BlockingCountingGateway implements SmsSendGateway {

        private final AtomicInteger calls = new AtomicInteger();
        private final long delayMillis;

        private BlockingCountingGateway(long delayMillis) {
            this.delayMillis = delayMillis;
        }

        @Override
        public SendResult send(String phone, String code) {
            calls.incrementAndGet();
            if (delayMillis > 0) {
                try {
                    Thread.sleep(delayMillis);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            }
            return SendResult.accepted("OK", "OK", "req-fake", "biz-fake");
        }

        int sendCalls() {
            return calls.get();
        }
    }
}

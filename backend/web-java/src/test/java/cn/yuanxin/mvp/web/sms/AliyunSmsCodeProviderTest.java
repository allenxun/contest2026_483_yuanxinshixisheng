package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * {@link AliyunSmsCodeProvider} 行为测试（假 gateway + 可推进时钟，<b>不</b>发真实短信）。
 * 覆盖随机码、一次性核销、尝试上限、TTL、三窗口节流与失败不回退。
 */
class AliyunSmsCodeProviderTest {

    private static final String FAKE_PHONE = "+8610000000000";
    private static final Instant START = Instant.parse("2026-01-01T00:00:00Z");

    private MutableClock clock;
    private RecordingGateway gateway;
    private InMemorySmsStateStore store;
    private AliyunSmsCodeProvider provider;

    @BeforeEach
    void setUp() {
        clock = new MutableClock(START, ZoneOffset.ofHours(8));
        gateway = new RecordingGateway();
        store = new InMemorySmsStateStore(new SmsRiskProperties(null, null, null, null, null, null));
        provider = new AliyunSmsCodeProvider(gateway,
                new SmsRiskProperties(null, null, null, null, null, null), clock, store);
    }

    // ---------- 成功路径 ----------

    @Test
    @DisplayName("Code=OK ⇒ 签发 challenge，验证码为 6 位随机且非 123456，且一次性核销")
    void okIssuesRandomCodeAndConsumesOnce() {
        SmsCodeProvider.ChallengeOutcome outcome = provider.issue(FAKE_PHONE, "login");
        String code = gateway.lastCode();
        assertThat(outcome.challengeId()).isNotBlank();
        assertThat(code).matches("\\d{6}").isNotEqualTo("123456");
        assertThat(provider.verify(outcome.challengeId(), code)).contains(FAKE_PHONE);
        assertThat(provider.verify(outcome.challengeId(), code)).isEmpty();
    }

    @Test
    @DisplayName("两次 issue 得到不同随机码（非固定 123456）")
    void twoIssuesProduceDifferentCodes() {
        provider.issue(FAKE_PHONE, "login");
        String first = gateway.lastCode();
        clock.advance(Duration.ofSeconds(61));
        provider.issue(FAKE_PHONE, "login");
        String second = gateway.lastCode();
        assertThat(first).isNotEqualTo(second);
        assertThat(first).isNotEqualTo("123456");
        assertThat(second).isNotEqualTo("123456");
    }

    // ---------- challengeId 碰撞：有界重生成，绝不签发未写入的 challenge ----------

    @Test
    @DisplayName("challengeId 碰撞时按上限重生成，最终签发真正写入的 challenge")
    void challengeIdCollisionIsRegenerated() {
        CollidingStore colliding = new CollidingStore(2);
        AliyunSmsCodeProvider collidingProvider = new AliyunSmsCodeProvider(gateway,
                new SmsRiskProperties(null, null, null, null, null, null), clock, colliding);

        SmsCodeProvider.ChallengeOutcome outcome = collidingProvider.issue(FAKE_PHONE, "login");

        assertThat(outcome.challengeId()).isNotBlank();
        assertThat(colliding.createCalls()).as("前 2 次碰撞 + 第 3 次成功").isEqualTo(3);
        assertThat(collidingProvider.verify(outcome.challengeId(), gateway.lastCode()))
                .contains(FAKE_PHONE);
    }

    @Test
    @DisplayName("challengeId 持续碰撞达上限 ⇒ fail-closed 503，绝不签发未写入的 challenge")
    void persistentChallengeIdCollisionFailsClosed() {
        CollidingStore colliding = new CollidingStore(Integer.MAX_VALUE);
        AliyunSmsCodeProvider collidingProvider = new AliyunSmsCodeProvider(gateway,
                new SmsRiskProperties(null, null, null, null, null, null), clock, colliding);

        ApiException failure = assertThrows(ApiException.class,
                () -> collidingProvider.issue(FAKE_PHONE, "login"));

        assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
        assertThat(failure.getHttpStatus()).isEqualTo(503);
        assertThat(colliding.createCalls())
                .isEqualTo(AliyunSmsCodeProvider.CHALLENGE_ID_MAX_ATTEMPTS);
        assertThat(colliding.challengeView()).isEmpty();
    }

    // ---------- 失败分类与"不回退、不签发" ----------

    @Test
    @DisplayName("平台流控 Code ⇒ 429 RATE_LIMITED + Retry-After，且不创建 challenge、不回退")
    void throttledMapsTo429WithoutChallenge() {
        gateway.next = SendResult.failed(FailureKind.THROTTLED, "isv.BUSINESS_LIMIT_CONTROL", "limit",
                "req", null);
        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(FAKE_PHONE, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.RATE_LIMITED);
        assertThat(failure.getHttpStatus()).isEqualTo(429);
        assertThat(failure.getHeaders()).containsKey("Retry-After");
        assertThat(failure.getDetails()).containsKey("retryAfterSeconds");
        assertThat(challenges()).isEmpty();
    }

    @Test
    @DisplayName("配置类失败 Code ⇒ 503 DEPENDENCY_UNAVAILABLE（消息注明不可重试），不创建 challenge")
    void configurationFailureMapsTo503() {
        gateway.next = SendResult.failed(FailureKind.CONFIGURATION, "isv.SMS_SIGNATURE_ILLEGAL", "sig",
                "req", null);
        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(FAKE_PHONE, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
        assertThat(failure.getHttpStatus()).isEqualTo(503);
        assertThat(failure.getMessage()).contains("not retryable");
        assertThat(challenges()).isEmpty();
    }

    @Test
    @DisplayName("依赖类失败 Code ⇒ 503，不创建 challenge")
    void dependencyFailureMapsTo503() {
        gateway.next = SendResult.failed(FailureKind.DEPENDENCY, "isp.SYSTEM_ERROR", "down",
                "req", null);
        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(FAKE_PHONE, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
        assertThat(challenges()).isEmpty();
    }

    @Test
    @DisplayName("响应缺 Code（应用层已判失败）⇒ 503，不创建 challenge")
    void missingCodeMapsTo503() {
        gateway.next = SendResult.failed(FailureKind.DEPENDENCY, null, "response missing Code", null, null);
        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(FAKE_PHONE, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
        assertThat(challenges()).isEmpty();
    }

    @Test
    @DisplayName("gateway 抛异常（超时/IO）⇒ 503，不创建 challenge、绝不回退替身")
    void gatewayExceptionMapsTo503() {
        AliyunSmsCodeProvider throwingProvider = new AliyunSmsCodeProvider((phone, code) -> {
            throw new IllegalStateException("read timed out");
        }, new SmsRiskProperties(null, null, null, null, null, null), clock);
        ApiException failure = assertThrows(ApiException.class,
                () -> throwingProvider.issue(FAKE_PHONE, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
    }

    // ---------- 风控 ----------

    @Test
    @DisplayName("过期后 verify 失败（TTL 300s）")
    void expiredChallengeFails() {
        SmsCodeProvider.ChallengeOutcome outcome = provider.issue(FAKE_PHONE, "login");
        clock.advance(Duration.ofSeconds(301));
        assertThat(provider.verify(outcome.challengeId(), gateway.lastCode())).isEmpty();
    }

    @Test
    @DisplayName("恰好用满尝试次数前正确码仍可用；超过上限后即使正确码也失败")
    void attemptLimit() {
        SmsCodeProvider.ChallengeOutcome ok = provider.issue(FAKE_PHONE, "login");
        String correct = gateway.lastCode();
        for (int i = 0; i < 4; i++) {
            assertThat(provider.verify(ok.challengeId(), "000000")).isEmpty();
        }
        assertThat(provider.verify(ok.challengeId(), correct)).contains(FAKE_PHONE);

        clock.advance(Duration.ofSeconds(61));
        SmsCodeProvider.ChallengeOutcome blocked = provider.issue(FAKE_PHONE, "login");
        String blockedCode = gateway.lastCode();
        for (int i = 0; i < 5; i++) {
            assertThat(provider.verify(blocked.challengeId(), "000000")).isEmpty();
        }
        assertThat(provider.verify(blocked.challengeId(), blockedCode)).isEmpty();
    }

    @Test
    @DisplayName("1 分钟窗口第 2 条被本地预检拒绝（未调用 gateway）")
    void minuteWindowThrottle() {
        provider.issue(FAKE_PHONE, "login");
        int callsAfterFirst = gateway.callCount();
        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(FAKE_PHONE, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.RATE_LIMITED);
        assertThat(gateway.callCount()).isEqualTo(callsAfterFirst);
    }

    @Test
    @DisplayName("1 小时窗口第 6 条被拒（61s 间隔，1 分钟窗口各 1 条）")
    void hourWindowThrottle() {
        for (int i = 0; i < 5; i++) {
            provider.issue(FAKE_PHONE, "login");
            clock.advance(Duration.ofSeconds(61));
        }
        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(FAKE_PHONE, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.RATE_LIMITED);
        assertThat(gateway.callCount()).isEqualTo(5);
    }

    @Test
    @DisplayName("1 天窗口第 11 条被拒（每小时 1 条，跨 10 小时）")
    void dayWindowThrottle() {
        for (int i = 0; i < 10; i++) {
            provider.issue(FAKE_PHONE, "login");
            clock.advance(Duration.ofMinutes(61));
        }
        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(FAKE_PHONE, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.RATE_LIMITED);
        assertThat(gateway.callCount()).isEqualTo(10);
    }

    @Test
    @DisplayName("UTC+8 自然日边界：跨日后恢复额度")
    void naturalDayBoundaryResets() {
        for (int i = 0; i < 10; i++) {
            provider.issue(FAKE_PHONE, "login");
            clock.advance(Duration.ofMinutes(61));
        }
        // 再推进越过 UTC+8 次日 00:00（当前约 10:10 UTC+8，推进 14 小时）
        clock.advance(Duration.ofHours(14));
        SmsCodeProvider.ChallengeOutcome outcome = provider.issue(FAKE_PHONE, "login");
        assertThat(outcome.challengeId()).isNotBlank();
    }

    /**
     * 等价可观测面：迁移前这里反射 {@code provider.challenges}，现在断言 store 的 challenge 视图。
     * 断言语义（"失败绝不创建 challenge"）不变。
     */
    private Map<String, ?> challenges() {
        return store.challengeView();
    }

    /** 记录调用并按 {@link #next} 返回。 */
    private static final class RecordingGateway implements SmsSendGateway {
        private final List<String[]> calls = new ArrayList<>();
        private SendResult next = SendResult.accepted("OK", "OK", "req-fake", "biz-fake");

        @Override
        public SendResult send(String phone, String code) {
            calls.add(new String[]{phone, code});
            return next;
        }

        int callCount() {
            return calls.size();
        }

        String lastCode() {
            return calls.isEmpty() ? null : calls.get(calls.size() - 1)[1];
        }
    }

    /**
     * 包装内存 store，强制 {@code createChallenge} 前 N 次返回 {@code false}（模拟 challengeId 碰撞），
     * 用于验证 provider 的有界重生成与"绝不签发未写入 challenge"的 fail-closed。
     */
    private static final class CollidingStore implements SmsStateStore {
        private final InMemorySmsStateStore delegate = new InMemorySmsStateStore(
                new SmsRiskProperties(null, null, null, null, null, null));
        private final int collisionsBeforeSuccess;
        private int createCalls;

        private CollidingStore(int collisionsBeforeSuccess) {
            this.collisionsBeforeSuccess = collisionsBeforeSuccess;
        }

        @Override
        public SendReservation reserveSend(String phone, Instant now) {
            return delegate.reserveSend(phone, now);
        }

        @Override
        public void commitSend(SendReservation reservation, Instant now) {
            delegate.commitSend(reservation, now);
        }

        @Override
        public void releaseSend(SendReservation reservation, boolean accepted) {
            delegate.releaseSend(reservation, accepted);
        }

        @Override
        public boolean createChallenge(String challengeId, String phone, String code,
                                       Instant now, int ttlSeconds) {
            createCalls++;
            if (createCalls <= collisionsBeforeSuccess) {
                return false;
            }
            return delegate.createChallenge(challengeId, phone, code, now, ttlSeconds);
        }

        @Override
        public Optional<String> consumeChallenge(String challengeId, String code,
                                                 Instant now, int maxAttempts) {
            return delegate.consumeChallenge(challengeId, code, now, maxAttempts);
        }

        int createCalls() {
            return createCalls;
        }

        Map<String, ?> challengeView() {
            return delegate.challengeView();
        }
    }
}

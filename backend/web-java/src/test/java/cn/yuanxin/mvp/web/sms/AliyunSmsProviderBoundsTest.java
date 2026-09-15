package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * IMPORTANT 8 有界内存测试：challenge 与 acceptedSends 均须机会式回收、有容量上限，
 * 且超限时 <b>fail-closed</b>（拒绝新签发），绝不静默丢弃有效 challenge 或放宽风控。
 * 全程内存 + 假 gateway，<b>绝不</b>发真实短信。
 *
 * <p>迁移后状态在 {@link InMemorySmsStateStore}：原反射 {@code provider.challenges} /
 * {@code provider.acceptedSends} 改为断言 store 的等价可观测面（{@link InMemorySmsStateStore#challengeView()}
 * / {@link InMemorySmsStateStore#acceptedSendsView()}），断言语义与强度不变。</p>
 */
class AliyunSmsProviderBoundsTest {

    private static final String PHONE_A = "+8610000000001";
    private static final String PHONE_B = "+8610000000002";
    private static final String PHONE_C = "+8610000000003";
    private static final Instant START = Instant.parse("2026-01-01T00:00:00Z");

    private static final SmsRiskProperties RISK =
            new SmsRiskProperties(null, null, null, null, null, null);

    private static InMemorySmsStateStore store(int maxChallenges, int maxTrackedPhones) {
        return new InMemorySmsStateStore(RISK, maxChallenges, maxTrackedPhones);
    }

    private static AliyunSmsCodeProvider provider(RecordingGateway gateway, MutableClock clock,
                                                  InMemorySmsStateStore store) {
        return new AliyunSmsCodeProvider(gateway, RISK, clock, store);
    }

    @Test
    @DisplayName("过期 challenge 在下一次 issue 时被机会式回收（store 中不再保留）")
    void expiredChallengesReclaimedOpportunistically() {
        MutableClock clock = new MutableClock(START, ZoneOffset.ofHours(8));
        RecordingGateway gateway = new RecordingGateway();
        InMemorySmsStateStore store = store(10_000, 10_000);
        AliyunSmsCodeProvider provider = provider(gateway, clock, store);

        SmsCodeProvider.ChallengeOutcome expired = provider.issue(PHONE_A, "login");
        clock.advance(Duration.ofSeconds(301)); // 超过 TTL 300s
        SmsCodeProvider.ChallengeOutcome fresh = provider.issue(PHONE_B, "login");

        assertThat(store.challengeView()).doesNotContainKey(expired.challengeId());
        assertThat(store.challengeView()).containsKey(fresh.challengeId()).hasSize(1);
    }

    @Test
    @DisplayName("尝试次数耗尽后 challenge 立即可回收（store 为空）")
    void attemptExhaustionReclaimsChallenge() {
        MutableClock clock = new MutableClock(START, ZoneOffset.ofHours(8));
        RecordingGateway gateway = new RecordingGateway();
        InMemorySmsStateStore store = store(10_000, 10_000);
        AliyunSmsCodeProvider provider = provider(gateway, clock, store);

        SmsCodeProvider.ChallengeOutcome outcome = provider.issue(PHONE_A, "login");
        for (int i = 0; i < 5; i++) {
            assertThat(provider.verify(outcome.challengeId(), "000000")).isEmpty();
        }
        assertThat(store.challengeView()).isEmpty();
    }

    @Test
    @DisplayName("challenge 容量超限：拒绝新签发（503）、不发短信、消息含上限但不含手机号")
    void challengeCapacityRejectsNewIssueFailClosed() {
        MutableClock clock = new MutableClock(START, ZoneOffset.ofHours(8));
        RecordingGateway gateway = new RecordingGateway();
        InMemorySmsStateStore store = store(2, 10_000);
        AliyunSmsCodeProvider provider = provider(gateway, clock, store);

        provider.issue(PHONE_A, "login");
        provider.issue(PHONE_B, "login");

        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(PHONE_C, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
        assertThat(failure.getHttpStatus()).isEqualTo(503);
        assertThat(failure.getMessage()).contains("max=2").doesNotContain(PHONE_C);
        assertThat(gateway.callCount()).as("容量拒绝必须发生在计费发送之前").isEqualTo(2);
        assertThat(store.challengeView()).hasSize(2);
    }

    @Test
    @DisplayName("acceptedSends 在保留窗口滑出后回收 phone key（不随进程无限增长）")
    void acceptedSendsKeyReclaimedAfterRetentionWindow() {
        MutableClock clock = new MutableClock(START, ZoneOffset.ofHours(8));
        RecordingGateway gateway = new RecordingGateway();
        InMemorySmsStateStore store = store(10_000, 10_000);
        AliyunSmsCodeProvider provider = provider(gateway, clock, store);

        provider.issue(PHONE_A, "login");
        assertThat(store.acceptedSendsView()).containsKey(PHONE_A);

        clock.advance(Duration.ofDays(2).plusSeconds(61));
        provider.issue(PHONE_B, "login"); // 触发机会式剪枝

        assertThat(store.acceptedSendsView()).doesNotContainKey(PHONE_A).containsKey(PHONE_B);
    }

    @Test
    @DisplayName("phone key 数量超限：拒绝新手机号签发（503），不丢弃既有节流历史")
    void trackedPhoneCapacityRejectsNewPhoneFailClosed() {
        MutableClock clock = new MutableClock(START, ZoneOffset.ofHours(8));
        RecordingGateway gateway = new RecordingGateway();
        InMemorySmsStateStore store = store(10_000, 1);
        AliyunSmsCodeProvider provider = provider(gateway, clock, store);

        provider.issue(PHONE_A, "login");

        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(PHONE_B, "login"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
        assertThat(failure.getHttpStatus()).isEqualTo(503);
        assertThat(failure.getMessage()).contains("max=1").doesNotContain(PHONE_B);
        assertThat(gateway.callCount()).isEqualTo(1);
        // 既有手机号的历史仍受保护，未被"丢最旧 key"放宽。
        assertThat(store.acceptedSendsView()).containsKey(PHONE_A);
    }

    private static final class RecordingGateway implements SmsSendGateway {
        private final List<String> calls = new ArrayList<>();

        @Override
        public SendResult send(String phone, String code) {
            calls.add(phone);
            return SendResult.accepted("OK", "OK", "req-fake", "biz-fake");
        }

        int callCount() {
            return calls.size();
        }
    }
}

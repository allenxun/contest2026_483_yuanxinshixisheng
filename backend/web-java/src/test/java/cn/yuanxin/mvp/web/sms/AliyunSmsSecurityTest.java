package cn.yuanxin.mvp.web.sms;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import cn.yuanxin.mvp.web.auth.AuthController;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.error.ApiException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * 脱敏硬约束测试：日志、异常消息、响应/挑战 DTO 均不得泄露验证码或完整手机号。
 * 使用明显假手机号 {@code +861****0000}（完整假值 {@code +8610000000000}）。
 */
class AliyunSmsSecurityTest {

    private static final String FAKE_PHONE = "+8610000000000";
    private static final String MASKED = "+861****0000";

    private static AliyunSmsProperties fakeProperties() {
        return new AliyunSmsProperties(null, null, "LTAI-FAKE-DO-NOT-USE",
                "FAKE-SECRET-DO-NOT-USE", null, "FAKE-SIGN", "SMS_FAKE_TEMPLATE", "code", null, null);
    }

    @Test
    @DisplayName("gateway 日志只出现掩码手机号，绝不出现完整手机号或验证码")
    void gatewayLogsAreMasked() {
        Logger logger = (Logger) LoggerFactory.getLogger(AliyunSmsSendGateway.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            String otp = "135790";
            AliyunSmsSendGateway ok = new AliyunSmsSendGateway(fakeProperties(), request -> {
                var body = new com.aliyun.dysmsapi20170525.models.SendSmsResponseBody()
                        .setCode("OK").setMessage("OK").setRequestId("r").setBizId("b");
                return body;
            });
            ok.send(FAKE_PHONE, otp);
            AliyunSmsSendGateway rejected = new AliyunSmsSendGateway(fakeProperties(), request -> {
                var body = new com.aliyun.dysmsapi20170525.models.SendSmsResponseBody()
                        .setCode("isv.BUSINESS_LIMIT_CONTROL").setMessage("limit").setRequestId("r");
                return body;
            });
            rejected.send(FAKE_PHONE, otp);

            assertThat(appender.list).isNotEmpty();
            for (String line : appender.list.stream()
                    .map(ILoggingEvent::getFormattedMessage).collect(Collectors.toList())) {
                assertThat(line).doesNotContain(FAKE_PHONE);
                assertThat(line).doesNotContain(otp);
            }
            assertThat(appender.list.stream().map(ILoggingEvent::getFormattedMessage).collect(Collectors.toList()))
                    .anyMatch(line -> line.contains(MASKED));
        } finally {
            logger.detachAppender(appender);
        }
    }

    @Test
    @DisplayName("provider 异常消息不含验证码/完整手机号")
    void providerExceptionMessagesAreMasked() {
        List<String> issuedCodes = new ArrayList<>();
        SmsSendGateway gateway = (phone, code) -> {
            issuedCodes.add(code);
            return SendResult.failed(FailureKind.CONFIGURATION, "isv.SMS_TEMPLATE_ILLEGAL", "bad", "r", null);
        };
        AliyunSmsCodeProvider provider = new AliyunSmsCodeProvider(gateway,
                new SmsRiskProperties(null, null, null, null, null, null), Clock.systemUTC());
        ApiException failure = assertThrows(ApiException.class, () -> provider.issue(FAKE_PHONE, "login"));
        assertThat(issuedCodes).hasSize(1);
        assertThat(failure.getMessage()).doesNotContain(FAKE_PHONE);
        assertThat(failure.getMessage()).doesNotContain(issuedCodes.get(0));
        assertThat(failure.getDetails() == null ? Map.of() : failure.getDetails())
                .doesNotContainKey("code");
    }

    @Test
    @DisplayName("ChallengeOutcome 与 f01 响应 DTO 均无验证码字段")
    void dtoHasNoCodeField() {
        assertThat(Arrays.stream(SmsCodeProvider.ChallengeOutcome.class.getRecordComponents())
                .map(java.lang.reflect.RecordComponent::getName))
                .containsExactly("challengeId", "retryAfterSeconds");
        assertThat(Arrays.stream(AuthController.SmsChallengeData.class.getRecordComponents())
                .map(java.lang.reflect.RecordComponent::getName))
                .containsExactly("challengeId", "retryAfter");
    }

    @Test
    @DisplayName("掩码函数保持首 4 尾 4")
    void maskingFormat() {
        assertThat(SmsMasking.maskPhone(FAKE_PHONE)).isEqualTo(MASKED);
        assertThat(SmsMasking.maskPhone(null)).isEqualTo("<none>");
        assertThat(SmsMasking.maskPhone("123")).isEqualTo("***");
    }

    @Test
    @DisplayName("阿里云模式断言：通用固定码 123456 不是有效验证码（内部生成的码绝不会是它）")
    void devFixedCodeNeverGenerated() {
        SmsSendGateway gateway = (phone, code) -> SendResult.accepted("OK", "OK", "r", "b");
        MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.ofHours(8));
        AliyunSmsCodeProvider provider = new AliyunSmsCodeProvider(gateway,
                new SmsRiskProperties(null, null, null, null, null, null), clock);
        for (int i = 0; i < 10; i++) {
            SmsCodeProvider.ChallengeOutcome outcome = provider.issue(FAKE_PHONE, "login");
            // 123456 在 aliyun 模式绝不成立。
            assertThat(provider.verify(outcome.challengeId(), "123456")).isEmpty();
            clock.advance(java.time.Duration.ofMinutes(61));
        }
    }
}

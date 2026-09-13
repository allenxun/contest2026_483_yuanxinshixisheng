package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.config.DisabledProvidersConfig;
import cn.yuanxin.mvp.web.config.ProvidersModeProductionGuard;
import cn.yuanxin.mvp.web.config.TestDoubleProvidersConfig;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.testdouble.SmsCodeDouble;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * 短信装配矩阵（{@link ApplicationContextRunner}，不启动 web/PG）。优先级：
 * {@code app.providers.mode=disabled} &gt; {@code app.sms.provider=aliyun} &gt; 默认 doubles。
 * 使用明显假凭据，不联网、不发短信。
 */
class SmsProvidersConfigTest {

    @Configuration
    @EnableConfigurationProperties({AppProperties.class, AliyunSmsProperties.class,
            SmsRiskProperties.class})
    static class PropsConfig {
    }

    @Configuration
    static class JdbcConfig {
        @Bean
        JdbcTemplate jdbcTemplate() {
            return org.mockito.Mockito.mock(JdbcTemplate.class);
        }
    }

    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class, DisabledProvidersConfig.class,
                        SmsProvidersConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    private static ApplicationContextRunner runnerWithGuard(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class, DisabledProvidersConfig.class,
                        SmsProvidersConfig.class, ProvidersModeProductionGuard.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    private static final String[] FAKE_ALIYUN = {
            "app.sms.provider=aliyun",
            "app.sms.aliyun.access-key-id=LTAI-FAKE-DO-NOT-USE",
            "app.sms.aliyun.access-key-secret=FAKE-SECRET-DO-NOT-USE",
            "app.sms.aliyun.sign-name=FAKE-SIGN",
            "app.sms.aliyun.template-code=SMS_FAKE_TEMPLATE"};

    @Test
    @DisplayName("mode=doubles + provider 缺省 → doubles 短信（123456 可用）")
    void defaultDoubles() {
        runner("local").withPropertyValues("app.env=dev").run(ctx -> {
            assertThat(ctx).hasNotFailed();
            SmsCodeProvider provider = ctx.getBean(SmsCodeProvider.class);
            assertThat(provider).isInstanceOf(SmsCodeDouble.class);
            SmsCodeProvider.ChallengeOutcome outcome = provider.issue("+8610000000001", "login");
            assertThat(provider.verify(outcome.challengeId(), "123456")).contains("+8610000000001");
        });
    }

    @Test
    @DisplayName("mode=doubles + provider=aliyun → 真实适配器（非 doubles）")
    void aliyunAdapterAssembled() {
        runner("local").withPropertyValues("app.env=dev").withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBean(SmsCodeProvider.class))
                            .isInstanceOf(AliyunSmsCodeProvider.class);
                });
    }

    @Test
    @DisplayName("mode=disabled + provider=aliyun → disabled 占位 503（aliyun 不装配）")
    void disabledWinsOverAliyun() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.providers.mode=disabled").withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    SmsCodeProvider provider = ctx.getBean(SmsCodeProvider.class);
                    assertThat(provider).isNotInstanceOf(AliyunSmsCodeProvider.class)
                            .isNotInstanceOf(SmsCodeDouble.class);
                    ApiException failure = assertThrows(ApiException.class,
                            () -> provider.issue("+8610000000001", "login"));
                    assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
                    assertThat(failure.getHttpStatus()).isEqualTo(503);
                });
    }

    @Test
    @DisplayName("mode=disabled + provider=doubles（缺省）→ 同一 disabled 占位")
    void disabledWithDoublesStillDisabled() {
        runner("local").withPropertyValues("app.env=dev", "app.providers.mode=disabled")
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    SmsCodeProvider provider = ctx.getBean(SmsCodeProvider.class);
                    assertThat(provider).isNotInstanceOf(SmsCodeDouble.class)
                            .isNotInstanceOf(AliyunSmsCodeProvider.class);
                    assertThrows(ApiException.class,
                            () -> provider.issue("+8610000000001", "login"));
                });
    }

    @Test
    @DisplayName("生产信号 + mode=doubles（provider 任意）→ 既有早期守卫仍拒绝，未被本轮绕过")
    void productionSignalStillRejected() {
        runnerWithGuard("prod")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles")
                .withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure()
                        .isInstanceOf(IllegalStateException.class)
                        .hasMessageContaining("app.providers.mode=doubles is not allowed"));
    }

    @Test
    @DisplayName("provider=aliyun 但缺必填键 → 拒绝启动且只列键名（不回显值）")
    void aliyunMissingKeysRefusesStartup() {
        runner("local").withPropertyValues("app.env=dev", "app.sms.provider=aliyun")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("app.sms.aliyun.access-key-id")
                            .hasMessageContaining("app.sms.aliyun.sign-name")
                            .hasMessageContaining("values are never logged")
                            .hasMessageNotContaining("FAKE-SECRET");
                });
    }
}

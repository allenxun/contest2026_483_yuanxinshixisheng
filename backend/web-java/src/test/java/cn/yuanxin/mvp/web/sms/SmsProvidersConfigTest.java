package cn.yuanxin.mvp.web.sms;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.config.DisabledProvidersConfig;
import cn.yuanxin.mvp.web.config.ProvidersModeProductionGuard;
import cn.yuanxin.mvp.web.config.TestDoubleProvidersConfig;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.state.AppStateProperties;
import cn.yuanxin.mvp.web.state.RedisStateConfig;
import cn.yuanxin.mvp.web.state.StateStoreConfigGuard;
import cn.yuanxin.mvp.web.testdouble.SmsCodeDouble;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * 短信装配矩阵（{@link ApplicationContextRunner}，不启动 web/PG）。优先级：
 * {@code app.providers.mode=disabled} &gt; {@code app.sms.provider=aliyun} &gt; 默认 doubles。
 * 维度：{@code app.state.provider}（memory 默认 / redis）；并纳入 {@link StateStoreConfigGuard}
 * 以锁定"真实短信 provider 必须配 Redis"的可执行门禁。使用明显假凭据，不联网、不发短信；
 * Redis 分支只注入 mock template（构造期不访问 Redis）。
 */
class SmsProvidersConfigTest {

    /**
     * 测试专用逃生门：假 gateway 单元测试用"aliyun + 内存状态"驱动编排逻辑，
     * 真实部署<b>禁止</b>使用（守卫会 WARN 且内存状态不跨实例、重启即失效）。
     */
    private static final String ESCAPE_HATCH = "app.state.allow-in-memory-with-real-sms=true";

    /** 守卫只检查该键"是否显式配置"（不读取值）；mock template 不会真正建连。 */
    private static final String REDIS_HOST = "spring.data.redis.host=127.0.0.1";

    @Configuration
    @EnableConfigurationProperties({AppProperties.class, AliyunSmsProperties.class,
            SmsRiskProperties.class, AppStateProperties.class})
    static class PropsConfig {
    }

    @Configuration
    static class JdbcConfig {
        @Bean
        JdbcTemplate jdbcTemplate() {
            return org.mockito.Mockito.mock(JdbcTemplate.class);
        }
    }

    @Configuration
    static class RedisTemplateConfig {
        @Bean
        StringRedisTemplate stringRedisTemplate() {
            // 仅装配用：RedisSmsStateStore 构造期不访问 Redis，mock 足以验证选择与注入。
            return org.mockito.Mockito.mock(StringRedisTemplate.class);
        }
    }

    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class, RedisTemplateConfig.class,
                        StateStoreConfigGuard.class, TestDoubleProvidersConfig.class,
                        DisabledProvidersConfig.class, RedisStateConfig.class,
                        SmsStateStoreConfig.class, SmsProvidersConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    private static ApplicationContextRunner runnerWithGuard(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class, RedisTemplateConfig.class,
                        StateStoreConfigGuard.class, TestDoubleProvidersConfig.class,
                        DisabledProvidersConfig.class, RedisStateConfig.class,
                        SmsStateStoreConfig.class, SmsProvidersConfig.class,
                        ProvidersModeProductionGuard.class)
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
    @DisplayName("mode=doubles + provider=aliyun + 逃生门 → 真实适配器（测试用假 gateway；真实部署禁止）")
    void aliyunAdapterAssembled() {
        runner("local").withPropertyValues("app.env=dev", ESCAPE_HATCH)
                .withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBean(SmsCodeProvider.class))
                            .isInstanceOf(AliyunSmsCodeProvider.class);
                });
    }

    @Test
    @DisplayName("mode=doubles + provider=aliyun + 逃生门 + state 缺省 → 内存 store（默认，行为不变）")
    void aliyunUsesInMemoryStateStoreByDefault() {
        runner("local").withPropertyValues("app.env=dev", ESCAPE_HATCH)
                .withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBean(SmsCodeProvider.class))
                            .isInstanceOf(AliyunSmsCodeProvider.class);
                    assertThat(ctx.getBean(SmsStateStore.class))
                            .isInstanceOf(InMemorySmsStateStore.class);
                });
    }

    @Test
    @DisplayName("mode=doubles + provider=aliyun + app.state.provider=redis → Redis store（跨实例实现）")
    void aliyunUsesRedisStateStoreWhenConfigured() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.state.provider=redis", REDIS_HOST).withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBean(SmsCodeProvider.class))
                            .isInstanceOf(AliyunSmsCodeProvider.class);
                    assertThat(ctx.getBean(SmsStateStore.class))
                            .isInstanceOf(RedisSmsStateStore.class);
                });
    }

    @Test
    @DisplayName("mode=disabled + provider=aliyun + app.state.provider=redis → disabled 仍最高优先级，无 store")
    void disabledWinsOverRedisStateStore() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.providers.mode=disabled", "app.state.provider=redis", REDIS_HOST)
                .withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    SmsCodeProvider provider = ctx.getBean(SmsCodeProvider.class);
                    assertThat(provider).isNotInstanceOf(AliyunSmsCodeProvider.class)
                            .isNotInstanceOf(SmsCodeDouble.class);
                    assertThat(ctx.getBeansOfType(SmsStateStore.class)).isEmpty();
                    ApiException failure = assertThrows(ApiException.class,
                            () -> provider.issue("+8610000000001", "login"));
                    assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
                });
    }

    @Test
    @DisplayName("mode=disabled + provider=aliyun → disabled 占位 503（aliyun 不装配，优先级最高）")
    void disabledWinsOverAliyun() {
        // 逃生门仅为让守卫不拦截这个"aliyun 配置存在但 mode=disabled"的用例；装配结果仍是 disabled。
        runner("local").withPropertyValues("app.env=dev",
                        "app.providers.mode=disabled", ESCAPE_HATCH).withPropertyValues(FAKE_ALIYUN)
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
    @DisplayName("真实短信 provider + 内存状态 + 未开逃生门 ⇒ 守卫拒绝启动（fail-closed）")
    void realSmsWithInMemoryStateIsRefusedByGuard() {
        runner("local").withPropertyValues("app.env=dev").withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .isInstanceOf(IllegalStateException.class)
                            .hasMessageContaining("app.state.provider=redis")
                            .hasMessageContaining(StateStoreConfigGuard.ALLOW_IN_MEMORY_WITH_REAL_SMS_KEY)
                            .hasMessageContaining("values are never logged")
                            .hasMessageNotContaining("FAKE-SECRET");
                });
    }

    @Test
    @DisplayName("逃生门打开 ⇒ 守卫 WARN 且仍装配内存 store（默认安全、显式声明可用）")
    void escapeHatchWarnsAndAssemblesInMemoryStore() {
        Logger logger = (Logger) LoggerFactory.getLogger(StateStoreConfigGuard.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            runner("local").withPropertyValues("app.env=dev", ESCAPE_HATCH)
                    .withPropertyValues(FAKE_ALIYUN)
                    .run(ctx -> {
                        assertThat(ctx).hasNotFailed();
                        assertThat(ctx.getBean(SmsCodeProvider.class))
                                .isInstanceOf(AliyunSmsCodeProvider.class);
                        assertThat(ctx.getBean(SmsStateStore.class))
                                .isInstanceOf(InMemorySmsStateStore.class);
                    });
            assertThat(appender.list.stream()
                    .filter(event -> Level.WARN.equals(event.getLevel()))
                    .map(ILoggingEvent::getFormattedMessage)
                    .collect(Collectors.toList()))
                    .as("逃生门放行必须留下 WARN")
                    .anyMatch(message -> message.contains("test escape hatch"));
        } finally {
            logger.detachAppender(appender);
        }
    }

    @Test
    @DisplayName("生产信号 + mode=doubles（provider 任意）→ 既有早期守卫仍拒绝，未被本轮绕过")
    void productionSignalStillRejected() {
        // 逃生门仅为避免新守卫抢跑，从而保留 ProvidersModeProductionGuard 的原始失败根因。
        runnerWithGuard("prod")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles", ESCAPE_HATCH)
                .withPropertyValues(FAKE_ALIYUN)
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure()
                        .isInstanceOf(IllegalStateException.class)
                        .hasMessageContaining("app.providers.mode=doubles is not allowed"));
    }

    @Test
    @DisplayName("provider=aliyun 但缺必填键 → 拒绝启动且只列键名（不回显值）")
    void aliyunMissingKeysRefusesStartup() {
        // 逃生门让新守卫不抢跑：本用例要断言的是"缺 aliyun 必填键"这一原始根因。
        runner("local").withPropertyValues("app.env=dev", ESCAPE_HATCH)
                .withPropertyValues("app.sms.provider=aliyun")
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

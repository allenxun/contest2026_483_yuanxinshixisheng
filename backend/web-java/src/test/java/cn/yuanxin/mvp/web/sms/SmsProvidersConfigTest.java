package cn.yuanxin.mvp.web.sms;

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
import org.springframework.boot.context.annotation.Configurations;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.AbstractApplicationContextRunner;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

import java.lang.reflect.Field;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * 短信装配矩阵（{@link ApplicationContextRunner}，不启动 web/PG）。优先级：
 * {@code app.providers.mode=disabled} &gt; {@code app.sms.provider=aliyun} &gt; 默认 doubles。
 * 维度：{@code app.state.provider}（memory 默认 / redis）。
 *
 * <p><b>为何不加载 {@link StateStoreConfigGuard}</b>（Oracle 第二十七轮裁定）：装配测试的职责是
 * "给定 provider/mode/state 组合，装配出哪个 bean"；守卫的职责是"哪些组合根本不允许启动"。
 * 把两者塞进同一个上下文，会迫使测试为了通过守卫而放宽生产规则（例如引入一个公开的运行时
 * 逃生门属性），从而在生产配置里留下合法绕过跨实例一致性要求的后门。正确做法是：守卫
 * <b>无条件拒绝</b>非法组合，其正向单元测试由 {@code web/state/**} 直接以 {@code MockEnvironment}
 * 调 {@code postProcessBeanFactory} 覆盖；本类的装配测试<b>只装配被测装配类</b>，因此可以合法地
 * 构造 "aliyun + 内存状态" 的 bean 组合。回归守卫见 {@link #runnerDoesNotLoadStateStoreGuard()}。</p>
 *
 * <p>使用明显假凭据，不联网、不发短信；Redis 分支只注入 mock template（构造期不访问 Redis），
 * 并给显式假 {@code spring.data.redis.host}（仅用于满足装配键存在性，不建连）。</p>
 */
class SmsProvidersConfigTest {

    /** 显式假 host（mock template，不真连接）；保留以覆盖"redis 配置齐全"的装配路径。 */
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

    /** 只装配被测装配类；**刻意不包含** {@link StateStoreConfigGuard}（见类级 javadoc）。 */
    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class, RedisTemplateConfig.class,
                        TestDoubleProvidersConfig.class, DisabledProvidersConfig.class,
                        RedisStateConfig.class, SmsStateStoreConfig.class, SmsProvidersConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    /** 额外加载既有 {@link ProvidersModeProductionGuard}（用于生产信号 + mode=doubles 的拒绝根因）。 */
    private static ApplicationContextRunner runnerWithGuard(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class, RedisTemplateConfig.class,
                        TestDoubleProvidersConfig.class, DisabledProvidersConfig.class,
                        RedisStateConfig.class, SmsStateStoreConfig.class, SmsProvidersConfig.class,
                        ProvidersModeProductionGuard.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    /** 反射读取 runner 实际注册的 configuration 类（用于回归守卫断言）。 */
    @SuppressWarnings("unchecked")
    private static List<Class<?>> configurationClasses(ApplicationContextRunner runner) throws Exception {
        Field runnerField = AbstractApplicationContextRunner.class.getDeclaredField("runnerConfiguration");
        runnerField.setAccessible(true);
        Object runnerConfiguration = runnerField.get(runner);
        Field configurationsField = runnerConfiguration.getClass().getDeclaredField("configurations");
        configurationsField.setAccessible(true);
        List<Configurations> configurations =
                (List<Configurations>) configurationsField.get(runnerConfiguration);
        return List.of(Configurations.getClasses(configurations));
    }

    private static final String[] FAKE_ALIYUN = {
            "app.sms.provider=aliyun",
            "app.sms.aliyun.access-key-id=LTAI-FAKE-DO-NOT-USE",
            "app.sms.aliyun.access-key-secret=FAKE-SECRET-DO-NOT-USE",
            "app.sms.aliyun.sign-name=FAKE-SIGN",
            "app.sms.aliyun.template-code=SMS_FAKE_TEMPLATE"};

    @Test
    @DisplayName("runner 不加载 StateStoreConfigGuard：装配测试与生产一致性守卫解耦")
    void runnerDoesNotLoadStateStoreGuard() throws Exception {
        assertThat(configurationClasses(runner("local")))
                .as("装配矩阵不得加载生产一致性守卫")
                .doesNotContain(StateStoreConfigGuard.class);
        assertThat(configurationClasses(runnerWithGuard("local")))
                .as("生产模式守卫存在时也不得混入状态守卫")
                .doesNotContain(StateStoreConfigGuard.class);
    }

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
    @DisplayName("mode=doubles + provider=aliyun + state 缺省 → 内存 store（默认，行为不变）")
    void aliyunUsesInMemoryStateStoreByDefault() {
        runner("local").withPropertyValues("app.env=dev").withPropertyValues(FAKE_ALIYUN)
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
                    assertThat(failure.getHttpStatus()).isEqualTo(503);
                });
    }

    @Test
    @DisplayName("mode=disabled + provider=aliyun → disabled 占位 503（aliyun 不装配，优先级最高）")
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

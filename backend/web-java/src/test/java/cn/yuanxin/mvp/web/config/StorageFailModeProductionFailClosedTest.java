package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * SC-C-05 存储失败注入缝的生产 fail-closed：生产信号下替身配置拒装，使
 * {@code APP_DOUBLE_STORAGE_FAIL_MODE} 在混合 profile（prod,dev）与矛盾组合
 * （prod profile + app.env=dev，即便显式 mode=doubles）下均不可达。本类为隔离上下文
 * runner，不启动 web 服务器；真实进程"端口未绑定"证据见交付报告。
 *
 * <p><b>本轮机制升级（增量 2：早期明确拒绝）：</b>上一轮解耦后，生产信号下
 * {@code TestDoubleProvidersConfig} 在<b>条件层</b>即不装配，失败根因退化为
 * {@code NoSuchBeanDefinitionException}（如"缺 SessionProvider/StoragePort"），
 * 把真正原因"生产信号下不允许 doubles"掩盖掉。本轮新增早于常规单例实例化的
 * {@link ProvidersModeProductionGuard}（{@code BeanFactoryPostProcessor}），在
 * {@code finishBeanFactoryInitialization} 之前抛出<b>诊断异常</b>。因此本类生产信号
 * 用例的根因由"缺 bean"改为"新守卫的 {@link IllegalStateException}"，并明确断言消息
 * 含 {@code app.providers.mode=doubles} 不允许 + 生产信号实际取值。</p>
 *
 * <p>断言强度对比（未弱化）：旧断言 = 启动失败 + 根因缺 StoragePort bean + 消息不含
 * {@code FileSystemStorageDouble}/{@code APP_DOUBLE_STORAGE_FAIL_MODE}；新断言 = 启动失败 +
 * 根因新守卫诊断（含 mode 与信号取值，诊断更明确）+ <b>同样保留</b>消息不含
 * {@code FileSystemStorageDouble}/{@code APP_DOUBLE_STORAGE_FAIL_MODE}（证明替身从未构造、
 * 注入开关不可达）。另因根因类型已是守卫 {@link IllegalStateException}，等价于排除了
 * {@code NoSuchBeanDefinitionException}。</p>
 */
class StorageFailModeProductionFailClosedTest {

    @Configuration
    @EnableConfigurationProperties(AppProperties.class)
    static class PropsConfig {
    }

    @Configuration
    static class JdbcConfig {
        @Bean
        JdbcTemplate jdbcTemplate() {
            // 本类只验证装配/fail-closed，不访问 DB；替身仅持有引用。
            return org.mockito.Mockito.mock(JdbcTemplate.class);
        }
    }

    /** 代表"应用真实需要 StoragePort"的消费者；守卫更早触发后它不会被实例化。 */
    record StoragePortConsumer(StoragePort storagePort) {
    }

    @Configuration
    static class StoragePortConsumerConfig {
        @Bean
        StoragePortConsumer storagePortConsumer(StoragePort storagePort) {
            return new StoragePortConsumer(storagePort);
        }
    }

    /** 不注册新守卫：仅验证 {@link TestDoubleProvidersConfig} 自身的条件层行为（隔离）。 */
    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    /**
     * 注册新守卫：生产信号 + doubles 时，守卫在 {@code BeanFactoryPostProcessor}
     * 阶段先于任何常规单例（含 StoragePort 消费者）实例化抛出诊断异常。
     */
    private static ApplicationContextRunner runnerWithProductionGuard(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class, StoragePortConsumerConfig.class,
                        ProvidersModeProductionGuard.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    /** 新守卫诊断的公共断言：根因是守卫异常、指出 mode=doubles 不被允许、且替身从未构造。 */
    private static void assertRefusedByProductionGuard(ApplicationContextRunner runner) {
        runner.run(ctx -> {
            assertThat(ctx).hasFailed();
            assertThat(ctx.getStartupFailure())
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("production fail-closed")
                    .hasMessageContaining("app.providers.mode=doubles")
                    .hasMessageContaining("production signals")
                    // 替身从未构造、注入开关从未被读取。
                    .hasMessageNotContaining("FileSystemStorageDouble")
                    .hasMessageNotContaining("APP_DOUBLE_STORAGE_FAIL_MODE");
        });
    }

    @Test
    @DisplayName("app.env=production + test profile + fail-put → 早期诊断拒绝（mode=doubles 不允许）")
    void productionEnvFailsClosed() {
        ApplicationContextRunner runner = runnerWithProductionGuard("test")
                .withPropertyValues("app.env=production",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put");
        assertRefusedByProductionGuard(runner);
        runner.run(ctx -> assertThat(ctx.getStartupFailure())
                .hasMessageContaining("app.env=production"));
    }

    @Test
    @DisplayName("混合 profile (prod,dev) + app.env=dev + mode=doubles + fail-put → 早期诊断拒绝（profile 判据）")
    void mixedProdDevProfileFailsClosed() {
        ApplicationContextRunner runner = runnerWithProductionGuard("prod", "dev")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put");
        assertRefusedByProductionGuard(runner);
        runner.run(ctx -> assertThat(ctx.getStartupFailure())
                .hasMessageContaining("app.env=dev")
                .hasMessageContaining("prod"));
    }

    @Test
    @DisplayName("app.env 大小写/空白容错：' Production ' 亦判生产信号（复用共享判据）")
    void productionEnvCaseInsensitiveAndTrimmed() {
        ApplicationContextRunner runner = runnerWithProductionGuard("test")
                .withPropertyValues("app.env= Production ",
                        "app.storage.dev-dir=target/storage-it/prod-guard-case",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put");
        assertRefusedByProductionGuard(runner);
        runner.run(ctx -> assertThat(ctx.getStartupFailure())
                .hasMessageContaining("app.env=Production"));
    }

    @Test
    @DisplayName("纯 prod profile → 不注册守卫时替身配置也不激活，绝不装配 StoragePort 替身")
    void prodProfileNeverAssemblesDouble() {
        // 注意：本用例刻意不注册 ProvidersModeProductionGuard，只验证条件层隔离行为；
        // “prod + doubles 被早期拒绝”由 ProductionGuard 的专用用例覆盖。
        runner("prod")
                .withPropertyValues("app.providers.mode=doubles")
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBeansOfType(StoragePort.class)).isEmpty();
                });
    }

    @Test
    @DisplayName("dev/test 非生产信号 → 允许装配且注入按 env 生效（不误伤）")
    void devTestSignalsAllowInjection() {
        runner("test")
                .withPropertyValues("app.env=test",
                        "app.storage.dev-dir=target/storage-it/prod-guard-control",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put:assessment_source")
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    StoragePort bean = ctx.getBean(StoragePort.class);
                    assertThat(bean).isInstanceOf(FileSystemStorageDouble.class);
                    assertThat(((FileSystemStorageDouble) bean).failPurposes())
                            .containsExactly("assessment_source");
                });
    }

    @Test
    @DisplayName("非法开关值在装配期 fail fast（不静默忽略）")
    void illegalFailModeFailsAtAssembly() {
        runner("test")
                .withPropertyValues("app.env=test",
                        "app.storage.dev-dir=target/storage-it/prod-guard-illegal",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put:not_a_purpose")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("APP_DOUBLE_STORAGE_FAIL_MODE"));
    }

    @Test
    @DisplayName("混合生产信号 → 早期诊断即拒（守卫异常，非缺 bean），替身从未构造、开关不可达")
    void productionSignalRefusesAssemblyBeforeAnyStoragePortExists() {
        // 刻意不探测固定端口：本类是非 web 的隔离 runner，硬编码端口会与同时运行真实应用
        // 的端到端验收 harness 冲突并报 BindException，证明力却极弱。"端口从未绑定"由真实
        // 进程证据承担（打包 jar 以 prod,dev + app.env=dev + mode=doubles 启动 → 退出码非 0）。
        ApplicationContextRunner runner = runnerWithProductionGuard("prod", "dev")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put");
        runner.run(ctx -> {
            assertThat(ctx).hasFailed();
            // 根因是新守卫的早期诊断，而不再是"缺 StoragePort bean"的 NoSuchBeanDefinitionException。
            assertThat(ctx.getStartupFailure())
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("app.providers.mode=doubles is not allowed")
                    .hasMessageContaining("production signals")
                    .hasMessageContaining("app.env=dev")
                    .hasMessageContaining("configure app.providers.mode=real");
            // 替身从未构造 ⇒ 注入开关不可达（消息层面直接证明）。
            assertThat(ctx.getStartupFailure())
                    .hasMessageNotContaining("FileSystemStorageDouble")
                    .hasMessageNotContaining("APP_DOUBLE_STORAGE_FAIL_MODE");
        });
    }
}

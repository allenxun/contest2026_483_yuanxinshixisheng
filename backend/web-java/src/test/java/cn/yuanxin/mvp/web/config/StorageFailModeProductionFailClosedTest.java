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
 * SC-C-05 存储失败注入缝的生产 fail-closed（双判据，对齐 DocsProductionGuard）：
 * 只要出现生产信号——激活 profile 含 {@code prod} <b>或</b> {@code app.env=production}
 * ——{@link TestDoubleProvidersConfig} 就拒绝装配（启动 fail fast），使
 * {@code APP_DOUBLE_STORAGE_FAIL_MODE} 在混合 profile（prod,dev）与矛盾组合
 * （prod profile + app.env=dev，即便显式 mode=doubles）下均不可达；纯 prod profile
 * 下配置根本不激活（替身不被装配）。本类为隔离上下文 runner，不启动 web 服务器；
 * 真实进程"端口未绑定"证据见交付报告。
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

    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    @Test
    @DisplayName("app.env=production + test profile + fail-put → 启动失败（替身拒装，开关不可达）")
    void productionEnvFailsClosed() {
        runner("test")
                .withPropertyValues("app.env=production",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("混合 profile (prod,dev) + app.env=dev + mode=doubles + fail-put → 启动失败（profile 判据）")
    void mixedProdDevProfileFailsClosed() {
        runner("prod", "dev")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("app.env 大小写/空白容错：' Production ' 亦判生产信号（对齐 DocsProductionGuard）")
    void productionEnvCaseInsensitiveAndTrimmed() {
        runner("test")
                .withPropertyValues("app.env= Production ",
                        "app.storage.dev-dir=target/storage-it/prod-guard-case",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("纯 prod profile → 替身配置不激活，绝不装配 StoragePort 替身")
    void prodProfileNeverAssemblesDouble() {
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
    @DisplayName("混合生产信号 → 装配期即拒（根因 IllegalStateException），且上下文不存在任何 StoragePort 替身")
    void productionSignalRefusesAssemblyBeforeAnyStoragePortExists() {
        // 刻意不探测固定端口：本类是非 web 的隔离 runner，硬编码端口（曾用 18083）会与
        // 同时运行真实应用的端到端验收 harness 冲突并报 BindException，证明力却极弱。
        // "端口从未绑定"由真实进程证据承担（打包 jar 以 prod,dev + app.env=dev + fail-put
        // 启动 → 退出码非 0、日志中 "Tomcat started on port" 出现 0 次、端口空闲）。
        runner("prod", "dev")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    // 拒装发生在 @Bean 装配期：根因必须是守卫抛出的 IllegalStateException，
                    // 且消息须体现双判据的实际取值（profile 命中、app.env 矛盾）。
                    assertThat(ctx.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class)
                            .hasStackTraceContaining("production fail-closed")
                            .hasStackTraceContaining("active-profile-prod=true")
                            .hasStackTraceContaining("app.env=dev");
                    // 拒装发生在 storagePort 这个 @Bean 的装配期：该 bean 无法被创建 ⇒
                    // 上下文中不存在任何可注入的 StoragePort 替身，注入开关在生产信号下不可达。
                    // 注意：启动失败的上下文**不能**用 doesNotHaveBean（AssertJ 要求上下文
                    // 启动成功，否则报 "but context failed to start"），故以"创建 storagePort
                    // bean 失败 + 无法实例化 StoragePort"作为等价且可断言的证据。
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("Error creating bean with name 'storagePort'")
                            .hasMessageContaining(
                                    "Failed to instantiate [cn.yuanxin.mvp.web.media.StoragePort]");
                });
    }
}

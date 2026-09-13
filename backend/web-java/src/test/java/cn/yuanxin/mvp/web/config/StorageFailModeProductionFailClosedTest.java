package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * SC-C-05 存储失败注入缝的生产 fail-closed（双判据，对齐 DocsProductionGuard）：
 * 只要出现生产信号——激活 profile 含 {@code prod} <b>或</b> {@code app.env=production}
 * ——{@link TestDoubleProvidersConfig} 就拒绝装配，使
 * {@code APP_DOUBLE_STORAGE_FAIL_MODE} 在混合 profile（prod,dev）与矛盾组合
 * （prod profile + app.env=dev，即便显式 mode=doubles）下均不可达；纯 prod profile
 * 下配置根本不激活（替身不被装配）。本类为隔离上下文 runner，不启动 web 服务器；
 * 真实进程"端口未绑定"证据见交付报告。
 *
 * <p><b>本轮机制变化（环境/实现解耦）：</b>此前 {@code TestDoubleProvidersConfig} 用
 * {@code @Profile(\{"dev","test"\})} 门，混合 {@code prod,dev} 因含 {@code dev} 而照常装配，
 * 再由 {@code storagePort()} 内 {@code requireNoProductionSignals} 在 <em>@Bean 装配期</em>
 * 抛 {@link IllegalStateException} 拒绝（根因是守卫异常）。解耦后替身配置改用共享
 * {@link NonProductionCondition}（{@code app.env != production} 且生效 profiles 不含
 * prod/production），<b>拒装在条件层提前发生</b>：混合 prod,dev 或 {@code app.env=production}
 * 时整个配置根本不装配，{@code StoragePort} 替身从不被构造（安全属性增强，非弱化）。</p>
 *
 * <p>因此本类对"生产信号"用例的断言随之改为：需要 {@code StoragePort} 的应用组件在
 * 启动时因 <b>缺 bean</b>（{@link NoSuchBeanDefinitionException}）失败，且失败消息中
 * <b>绝不出现</b> {@code FileSystemStorageDouble} / {@code APP_DOUBLE_STORAGE_FAIL_MODE}
 * ——直接证明替身未构造、注入开关不可达。断言强度不降：仍锁定失败信号、失败根因、
 * 开关不可达三点。</p>
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

    /** 代表"应用真实需要 StoragePort"的消费者，用于把"替身未装配"暴露为启动失败。 */
    record StoragePortConsumer(StoragePort storagePort) {
    }

    @Configuration
    static class StoragePortConsumerConfig {
        @Bean
        StoragePortConsumer storagePortConsumer(StoragePort storagePort) {
            return new StoragePortConsumer(storagePort);
        }
    }

    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    /** 追加依赖 StoragePort 的消费者：替身被拒装 ⇒ 消费者无法创建 ⇒ 上下文启动失败。 */
    private static ApplicationContextRunner runnerRequiringStoragePort(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class, StoragePortConsumerConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    @Test
    @DisplayName("app.env=production + test profile + fail-put → 启动失败（替身拒装，开关不可达）")
    void productionEnvFailsClosed() {
        runnerRequiringStoragePort("test")
                .withPropertyValues("app.env=production",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    // 拒装提前到条件层：根因是缺 StoragePort bean（而非守卫异常）。
                    assertThat(ctx.getStartupFailure())
                            .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class)
                            .hasStackTraceContaining("No qualifying bean of type"
                                    + " 'cn.yuanxin.mvp.web.media.StoragePort' available")
                            // 替身从未构造、注入开关从未被读取。
                            .hasMessageNotContaining("FileSystemStorageDouble")
                            .hasMessageNotContaining("APP_DOUBLE_STORAGE_FAIL_MODE");
                });
    }

    @Test
    @DisplayName("混合 profile (prod,dev) + app.env=dev + mode=doubles + fail-put → 启动失败（profile 判据）")
    void mixedProdDevProfileFailsClosed() {
        runnerRequiringStoragePort("prod", "dev")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class)
                            .hasMessageNotContaining("FileSystemStorageDouble")
                            .hasMessageNotContaining("APP_DOUBLE_STORAGE_FAIL_MODE");
                });
    }

    @Test
    @DisplayName("app.env 大小写/空白容错：' Production ' 亦判生产信号（对齐 DocsProductionGuard）")
    void productionEnvCaseInsensitiveAndTrimmed() {
        runnerRequiringStoragePort("test")
                .withPropertyValues("app.env= Production ",
                        "app.storage.dev-dir=target/storage-it/prod-guard-case",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class)
                            .hasMessageNotContaining("FileSystemStorageDouble")
                            .hasMessageNotContaining("APP_DOUBLE_STORAGE_FAIL_MODE");
                });
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
    @DisplayName("混合生产信号 → 条件层即拒装（缺 bean 启动失败），替身从未构造、开关不可达")
    void productionSignalRefusesAssemblyBeforeAnyStoragePortExists() {
        // 刻意不探测固定端口：本类是非 web 的隔离 runner，硬编码端口（曾用 18083）会与
        // 同时运行真实应用的端到端验收 harness 冲突并报 BindException，证明力却极弱。
        // "端口从未绑定"由真实进程证据承担（打包 jar 以 prod,dev + app.env=dev + fail-put
        // 启动 → 退出码非 0、日志中 "Tomcat started on port" 出现 0 次、端口空闲）。
        runnerRequiringStoragePort("prod", "dev")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    // 机制变化：解耦后拒装发生在条件层，替身配置整体不装配，故依赖
                    // StoragePort 的消费者因“无此 bean”失败（而非旧守卫抛 IllegalStateException）。
                    assertThat(ctx.getStartupFailure())
                            .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class)
                            .hasStackTraceContaining("No qualifying bean of type"
                                    + " 'cn.yuanxin.mvp.web.media.StoragePort' available")
                            .hasMessageContaining("storagePortConsumer");
                    // 替身从未构造 ⇒ 上下文不存在任何可注入的 StoragePort 替身，
                    // 注入开关在生产信号下不可达（消息层面直接证明）。
                    assertThat(ctx.getStartupFailure())
                            .hasMessageNotContaining("FileSystemStorageDouble")
                            .hasMessageNotContaining("APP_DOUBLE_STORAGE_FAIL_MODE");
                });
    }
}

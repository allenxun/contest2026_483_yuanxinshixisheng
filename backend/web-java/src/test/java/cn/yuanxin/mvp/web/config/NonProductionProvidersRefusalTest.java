package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.devices.proof.ConnectionProofVerifier;
import cn.yuanxin.mvp.web.devices.proof.DeviceProofDoublesConfig;
import cn.yuanxin.mvp.web.devices.proof.PairingProofVerifier;
import cn.yuanxin.mvp.web.identity.FaceIdentityResolver;
import cn.yuanxin.mvp.web.identity.IdentityProvidersConfig;
import cn.yuanxin.mvp.web.media.StoragePort;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 生产/矛盾配置下替身配置拒装的隔离上下文断言（{@link ApplicationContextRunner}，
 * 不启动 web/PG）。覆盖 {@link TestDoubleProvidersConfig}/{@link DeviceProofDoublesConfig}/
 * {@link IdentityProvidersConfig} 的全部替身端口：生产信号下它们<b>一个都不装配</b>
 * （环境/实现解耦后，拒装在条件层发生）。
 *
 * <p>与 {@link StorageFailModeProductionFailClosedTest} 的分工：后者用"依赖 StoragePort
 * 的消费者"把拒装放大为启动失败并锁定失败根因；本类直接断言各端口替身 bean 不存在。</p>
 */
class NonProductionProvidersRefusalTest {

    @Configuration
    @EnableConfigurationProperties(AppProperties.class)
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
                        TestDoubleProvidersConfig.class, DeviceProofDoublesConfig.class,
                        IdentityProvidersConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    private static void assertNoDoubleAssembled(ApplicationContextRunner runner) {
        runner.run(ctx -> {
            assertThat(ctx).hasNotFailed();
            assertThat(ctx.getBeansOfType(SessionProvider.class)).isEmpty();
            assertThat(ctx.getBeansOfType(SmsCodeProvider.class)).isEmpty();
            assertThat(ctx.getBeansOfType(FaceProvider.class)).isEmpty();
            assertThat(ctx.getBeansOfType(StoragePort.class)).isEmpty();
            assertThat(ctx.getBeansOfType(FaceIdentityResolver.class)).isEmpty();
            assertThat(ctx.getBeansOfType(PairingProofVerifier.class)).isEmpty();
            assertThat(ctx.getBeansOfType(ConnectionProofVerifier.class)).isEmpty();
        });
    }

    @Test
    @DisplayName("prod profile（app.env=dev, mode=doubles）→ 替身全部不装配")
    void prodProfileAssemblesNothing() {
        assertNoDoubleAssembled(runner("prod")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles"));
    }

    @Test
    @DisplayName("production profile（app.env=dev, mode=doubles）→ 替身全部不装配")
    void productionProfileAssemblesNothing() {
        assertNoDoubleAssembled(runner("production")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles"));
    }

    @Test
    @DisplayName("混合 prod,dev + app.env=dev + mode=doubles → 替身全部不装配（不因含 dev 放行）")
    void mixedProdDevAssemblesNothing() {
        assertNoDoubleAssembled(runner("prod", "dev")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles"));
    }

    @Test
    @DisplayName("app.env=production + test profile + mode=doubles → 替身全部不装配")
    void productionEnvAssemblesNothing() {
        assertNoDoubleAssembled(runner("test")
                .withPropertyValues("app.env=production", "app.providers.mode=doubles"));
    }

    @Test
    @DisplayName("正向对照：local profile 替身全部装配（环境与实现解耦后不再要求 dev/test）")
    void localProfileAssemblesEverything() {
        runner("local")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles")
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBeansOfType(SessionProvider.class)).hasSize(1);
                    assertThat(ctx.getBeansOfType(StoragePort.class)).hasSize(1);
                    assertThat(ctx.getBeansOfType(FaceIdentityResolver.class)).hasSize(1);
                    assertThat(ctx.getBeansOfType(PairingProofVerifier.class)).hasSize(1);
                    assertThat(ctx.getBeansOfType(ConnectionProofVerifier.class)).hasSize(1);
                });
    }
}

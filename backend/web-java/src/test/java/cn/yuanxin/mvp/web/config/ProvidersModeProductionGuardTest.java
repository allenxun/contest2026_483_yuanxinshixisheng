package cn.yuanxin.mvp.web.config;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * {@link ProvidersModeProductionGuard} 隔离测试：生产信号 + {@code mode=doubles}
 * 必须由<b>早期守卫</b>明确拒绝（诊断异常），覆盖四种生产/矛盾组合，并锁定
 * {@code real}/{@code disabled} 与非生产环境不被误伤。{@link ApplicationContextRunner}
 * 不启动 web/PG。
 */
class ProvidersModeProductionGuardTest {

    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(ProvidersModeProductionGuard.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    private static ApplicationContextRunner prodProfile() {
        return runner("prod");
    }

    @Test
    @DisplayName("prod profile + doubles → 早期拒绝（mode=doubles 在生产信号下不允许）")
    void prodProfileWithDoublesIsRefused() {
        prodProfile()
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure()
                        .isInstanceOf(IllegalStateException.class)
                        .hasMessageContaining("production fail-closed")
                        .hasMessageContaining("app.providers.mode=doubles")
                        .hasMessageContaining("production signals")
                        .hasMessageContaining("app.env=dev"));
    }

    @Test
    @DisplayName("字面 production profile + doubles → 早期拒绝（不再漏判 production）")
    void productionLiteralProfileWithDoublesIsRefused() {
        runner("production")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure()
                        .isInstanceOf(IllegalStateException.class)
                        .hasMessageContaining("app.providers.mode=doubles"));
    }

    @Test
    @DisplayName("混合 prod,dev + app.env=dev + doubles → 早期拒绝（此前被缺 SessionProvider 掩盖）")
    void mixedProdDevWithDoublesIsRefused() {
        runner("prod", "dev")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure()
                        .isInstanceOf(IllegalStateException.class)
                        .hasMessageContaining("app.providers.mode=doubles")
                        .hasMessageContaining("app.env=dev"));
    }

    @Test
    @DisplayName("app.env=production + test profile + doubles → 早期拒绝")
    void productionEnvWithDoublesIsRefused() {
        runner("test")
                .withPropertyValues("app.env=production", "app.providers.mode=doubles")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure()
                        .isInstanceOf(IllegalStateException.class)
                        .hasMessageContaining("app.providers.mode=doubles")
                        .hasMessageContaining("app.env=production"));
    }

    @Test
    @DisplayName("mode=doubles 缺省（未配置）在生产信号下也被拒绝（matchIfMissing 语义）")
    void missingModeDefaultsToDoublesAndIsRefused() {
        prodProfile()
                .withPropertyValues("app.env=dev")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("app.providers.mode=doubles"));
    }

    // ---------- 不误伤 ----------

    @Test
    @DisplayName("非生产（local）+ doubles → 守卫放行")
    void nonProductionDoublesPasses() {
        runner("local")
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }

    @Test
    @DisplayName("prod profile + mode=real → 守卫放行（由 ProductionFailClosedValidator 做实现完备性校验）")
    void prodProfileWithRealPassesGuard() {
        prodProfile()
                .withPropertyValues("app.env=dev", "app.providers.mode=real")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }

    @Test
    @DisplayName("prod profile + mode=disabled → 守卫放行（显式关闭能力，允许启动）")
    void prodProfileWithDisabledPassesGuard() {
        prodProfile()
                .withPropertyValues("app.env=dev", "app.providers.mode=disabled")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }
}

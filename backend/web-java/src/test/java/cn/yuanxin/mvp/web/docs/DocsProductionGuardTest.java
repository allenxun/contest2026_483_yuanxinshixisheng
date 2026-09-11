package cn.yuanxin.mvp.web.docs;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 生产 fail-closed 护栏的轻量隔离测试（{@link ApplicationContextRunner}，
 * 不启动 web/PG 上下文，不额外占用堆）。
 *
 * <p>覆盖 Oracle BLOCKER 的每个复现：护栏不能只认 {@code app.env=production}，
 * 否则 {@code prod} profile 被 {@code app.env=dev} 覆盖时 springdoc 自动配置
 * 仍会暴露端点。同时覆盖文档开关的缺省语义（未显式 false 即视为可能开启）。</p>
 */
class DocsProductionGuardTest {

    /** 每次新建 runner，避免共享状态；护栏无条件注册（BLOCKER 修复）。 */
    private static ApplicationContextRunner runner() {
        return new ApplicationContextRunner()
                .withUserConfiguration(DocsProductionGuard.class);
    }

    private static ApplicationContextRunner prodProfile() {
        return runner().withInitializer(
                ctx -> ctx.getEnvironment().setActiveProfiles("prod"));
    }

    // ---------- BLOCKER 复现 ----------

    @Test
    @DisplayName("BLOCKER：prod profile + app.env=dev + api-docs=true → 启动失败（profile 信号独立生效）")
    void prodProfileWithDevEnvAndApiDocsEnabledFails() {
        prodProfile()
                .withPropertyValues("app.env=dev", "springdoc.api-docs.enabled=true")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("BLOCKER：prod profile + app.env=dev + swagger-ui=true（api-docs 未显式开）→ 启动失败")
    void prodProfileWithDevEnvAndSwaggerUiEnabledFails() {
        prodProfile()
                .withPropertyValues("app.env=dev", "springdoc.swagger-ui.enabled=true")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("缺省语义：prod profile + app.env=dev 且两个开关都未配置 → 保守视为开启，启动失败")
    void prodProfileWithUnsetSwitchesTreatedAsEnabled() {
        prodProfile()
                .withPropertyValues("app.env=dev")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    // ---------- 回归（Oracle 明确要求） ----------

    @Test
    @DisplayName("回归：app.env=production + dev profile + 文档开启 → 启动失败")
    void productionEnvWithDevProfileAndDocsEnabledFails() {
        runner()
                .withPropertyValues("app.env=production",
                        "springdoc.api-docs.enabled=true", "springdoc.swagger-ui.enabled=true")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    // ---------- 不误伤 ----------

    @Test
    @DisplayName("生产信号成立但两个开关都显式 false → 正常启动")
    void productionWithBothSwitchesExplicitlyDisabledStarts() {
        runner()
                .withPropertyValues("app.env=production",
                        "springdoc.api-docs.enabled=false", "springdoc.swagger-ui.enabled=false")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }

    @Test
    @DisplayName("prod profile 但两个开关都显式 false → 正常启动（不误伤）")
    void prodProfileWithBothSwitchesExplicitlyDisabledStarts() {
        prodProfile()
                .withPropertyValues("app.env=dev",
                        "springdoc.api-docs.enabled=false", "springdoc.swagger-ui.enabled=false")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }

    @Test
    @DisplayName("非生产：dev profile + app.env=dev + 文档开启 → 正常启动（开发态可用）")
    void devWithDocsEnabledStarts() {
        runner()
                .withPropertyValues("app.env=dev", "springdoc.api-docs.enabled=true")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }
}

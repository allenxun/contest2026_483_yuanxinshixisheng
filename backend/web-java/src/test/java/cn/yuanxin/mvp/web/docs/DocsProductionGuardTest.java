package cn.yuanxin.mvp.web.docs;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 生产 fail-closed 护栏的轻量隔离测试（{@link ApplicationContextRunner}，
 * 不启动 web/PG 上下文，不额外占用堆）。
 *
 * <p>证明：{@code app.env=production} 且 springdoc 任一开关为 true 时上下文启动失败；
 * 关闭时不注册护栏、不失败；dev 下护栏条件不满足（不参与）。</p>
 */
class DocsProductionGuardTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(DocsProductionGuard.class);

    @Test
    @DisplayName("production + api-docs 启用 → 启动失败（fail closed）")
    void productionWithApiDocsEnabledFails() {
        runner.withPropertyValues("app.env=production", "springdoc.api-docs.enabled=true")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("production + swagger-ui 启用 → 启动失败（fail closed）")
    void productionWithSwaggerUiEnabledFails() {
        runner.withPropertyValues("app.env=production", "springdoc.swagger-ui.enabled=true")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("production + 两项均关闭 → 正常启动（护栏不误伤）")
    void productionWithDocsDisabledStarts() {
        runner.withPropertyValues("app.env=production",
                        "springdoc.api-docs.enabled=false", "springdoc.swagger-ui.enabled=false")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }

    @Test
    @DisplayName("dev + 启用 → 护栏条件不满足，不介入（正常启动）")
    void devDoesNotActivateGuard() {
        runner.withPropertyValues("app.env=dev", "springdoc.api-docs.enabled=true")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }
}

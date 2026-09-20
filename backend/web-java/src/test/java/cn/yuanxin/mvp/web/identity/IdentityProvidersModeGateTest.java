package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.care.CareFaceVerifier;
import cn.yuanxin.mvp.web.care.FailClosedCareFaceVerifier;
import cn.yuanxin.mvp.web.care.MemberBindingFaceDouble;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 增量 1 的装配证据：两个测试提供者（{@link IdentityProvidersConfig} 的
 * {@link DevTestFaceIdentityResolver}、{@link MemberBindingFaceDouble}）仅在
 * {@code app.providers.mode=doubles}（默认）且非生产环境装配；{@code mode=disabled}
 * 由 {@link DisabledFaceIdentityResolverConfig} 兜底（可启动、运行时 503）；
 * {@code mode=real} 下无 {@link FaceIdentityResolver} bean → 启动失败（既有刻意 fail-closed）。
 * 隔离 runner，不启动 web/PG。
 */
class IdentityProvidersModeGateTest {

    record FaceIdentityResolverConsumer(FaceIdentityResolver resolver) {
    }

    @Configuration
    static class FaceIdentityResolverConsumerConfig {
        @Bean
        FaceIdentityResolverConsumer faceIdentityResolverConsumer(FaceIdentityResolver resolver) {
            return new FaceIdentityResolverConsumer(resolver);
        }
    }

    private static ApplicationContextRunner runner(String mode, String... profiles) {
        ApplicationContextRunner r = new ApplicationContextRunner()
                .withUserConfiguration(IdentityProvidersConfig.class,
                        DisabledFaceIdentityResolverConfig.class,
                        MemberBindingFaceDouble.class, FailClosedCareFaceVerifier.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
        return mode == null ? r : r.withPropertyValues("app.providers.mode=" + mode);
    }

    @Test
    @DisplayName("mode=doubles（默认，非生产）：两个测试替身均装配")
    void doublesProfileAssemblesBothTestDoubles() {
        runner(null, "local").withPropertyValues("app.env=dev").run(ctx -> {
            assertThat(ctx).hasNotFailed();
            assertInstanceOf(DevTestFaceIdentityResolver.class, ctx.getBean(FaceIdentityResolver.class));
            assertInstanceOf(MemberBindingFaceDouble.class, ctx.getBean(CareFaceVerifier.class));
        });
    }

    @Test
    @DisplayName("mode=disabled（非生产）：可启动；FaceIdentityResolver 为 503 占位，护理核验落到 FailClosed")
    void disabledAssemblesPlaceholdersNotTestDoubles() {
        runner("disabled", "local").withPropertyValues("app.env=dev").run(ctx -> {
            assertThat(ctx).hasNotFailed();

            FaceIdentityResolver resolver = ctx.getBean(FaceIdentityResolver.class);
            assertThat(resolver).isNotInstanceOf(DevTestFaceIdentityResolver.class);
            ApiException disabled = assertThrows(ApiException.class,
                    () -> resolver.resolve(new byte[]{1}, FaceClassification.MATCHED));
            assertThat(disabled.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
            assertThat(disabled.getMessage()).contains("capability disabled by configuration");
            assertThrows(ApiException.class, resolver::identityNamespace);

            assertInstanceOf(FailClosedCareFaceVerifier.class, ctx.getBean(CareFaceVerifier.class));
            assertThat(ctx.getBeansOfType(MemberBindingFaceDouble.class)).isEmpty();
        });
    }

    @Test
    @DisplayName("mode=real（非生产）：两个测试替身均不装配；FaceIdentityResolver 缺失 → 启动失败（刻意 fail-closed）")
    void realRefusesTestDoublesAndFailsClosed() {
        runner("real", "local").withPropertyValues("app.env=dev")
                .withUserConfiguration(FaceIdentityResolverConsumerConfig.class)
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("FaceIdentityResolver")
                            .hasMessageNotContaining("DevTestFaceIdentityResolver")
                            .hasMessageNotContaining("MemberBindingFaceDouble");
                });
    }

    @Test
    @DisplayName("mode=disabled（非生产）暴露副作用：不返回“可靠匹配”，一律 503")
    void disabledNeverFakesReliableMatch() {
        runner("disabled", "local").withPropertyValues("app.env=dev").run(ctx -> {
            FaceIdentityResolver resolver = ctx.getBean(FaceIdentityResolver.class);
            assertNotNull(resolver);
            for (FaceClassification classification : FaceClassification.values()) {
                ApiException e = assertThrows(ApiException.class,
                        () -> resolver.resolve(new byte[]{9}, classification));
                assertTrue(e.getMessage().contains("face-identity"));
            }
        });
    }
}

package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.care.CareFaceVerifier;
import cn.yuanxin.mvp.web.care.FailClosedCareFaceVerifier;
import cn.yuanxin.mvp.web.care.MemberBindingFaceDouble;
import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.config.DisabledProvidersConfig;
import cn.yuanxin.mvp.web.config.ProvidersModeProductionGuard;
import cn.yuanxin.mvp.web.config.TestDoubleProvidersConfig;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.identity.DevTestFaceIdentityResolver;
import cn.yuanxin.mvp.web.identity.DisabledFaceIdentityResolverConfig;
import cn.yuanxin.mvp.web.identity.FaceIdentityResolver;
import cn.yuanxin.mvp.web.identity.IdentityProvidersConfig;
import cn.yuanxin.mvp.web.testdouble.FaceProviderDouble;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * 人脸装配矩阵（{@link ApplicationContextRunner}，不启动 web/PG、不访问真实人脸服务）。
 * 优先级：{@code app.providers.mode=disabled} &gt; {@code app.face.provider}；
 * {@code provider=aliyun} 拒绝启动；insightface 下三个 doubles 均不装配。
 */
class FaceProvidersConfigTest {

    @Configuration
    @EnableConfigurationProperties({AppProperties.class, InsightFaceProperties.class,
            AliyunFaceProperties.class})
    static class PropsConfig {
        @Bean
        JdbcTemplate jdbcTemplate() {
            return org.mockito.Mockito.mock(JdbcTemplate.class);
        }

        @Bean
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }
    }

    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, TestDoubleProvidersConfig.class,
                        IdentityProvidersConfig.class, MemberBindingFaceDouble.class,
                        FailClosedCareFaceVerifier.class, DisabledProvidersConfig.class,
                        DisabledFaceIdentityResolverConfig.class, FaceProvidersConfig.class,
                        AliyunFaceBoundaryConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    private static String[] insightface() {
        return new String[]{
                "app.face.provider=insightface",
                "app.face.insightface.base-url=http://10.3.6.163:8010",
                "app.face.insightface.namespace=openvela-mvp",
                "app.face.insightface.internal-token=FAKE-INTERNAL-TOKEN-DO-NOT-USE"};
    }

    @Test
    @DisplayName("provider=doubles（缺省）→ 三个 doubles 均在（既有行为不变）")
    void defaultDoubles() {
        runner("local").withPropertyValues("app.env=dev").run(ctx -> {
            assertThat(ctx).hasNotFailed();
            assertInstanceOf(FaceProviderDouble.class, ctx.getBean(FaceProvider.class));
            assertInstanceOf(DevTestFaceIdentityResolver.class, ctx.getBean(FaceIdentityResolver.class));
            assertInstanceOf(MemberBindingFaceDouble.class, ctx.getBean(CareFaceVerifier.class));
        });
    }

    @Test
    @DisplayName("provider=insightface → 三个 doubles 均不在；Unavailable 解析器恒 empty；provider/verifier 为真实实现")
    void insightfaceReplacesDoubles() {
        runner("local").withPropertyValues("app.env=dev").withPropertyValues(insightface())
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertInstanceOf(InsightFaceProvider.class, ctx.getBean(FaceProvider.class));
                    FaceIdentityResolver resolver = ctx.getBean(FaceIdentityResolver.class);
                    assertInstanceOf(UnavailableFaceIdentityResolver.class, resolver);
                    assertThat(resolver.identityNamespace()).isEqualTo("openvela-mvp");
                    assertThat(resolver.resolve(new byte[]{1}, FaceClassification.MATCHED)).isEmpty();
                    assertInstanceOf(InsightFaceCareVerifier.class, ctx.getBean(CareFaceVerifier.class));

                    assertThat(ctx.getBeansOfType(FaceProviderDouble.class)).isEmpty();
                    assertThat(ctx.getBeansOfType(DevTestFaceIdentityResolver.class)).isEmpty();
                    assertThat(ctx.getBeansOfType(MemberBindingFaceDouble.class)).isEmpty();
                });
    }

    @Test
    @DisplayName("provider=aliyun → 拒绝启动（未实现，仅配置边界）")
    void aliyunRefusesStartup() {
        runner("local").withPropertyValues("app.env=dev", "app.face.provider=aliyun")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("app.face.provider=aliyun is not implemented")
                            .hasMessageContaining("doubles")
                            .hasMessageContaining("insightface");
                });
    }

    @Test
    @DisplayName("mode=disabled + provider=insightface → disabled 占位优先（真实实现不装配）")
    void disabledWinsOverInsightface() {
        runner("local").withPropertyValues("app.env=dev", "app.providers.mode=disabled")
                .withPropertyValues(insightface())
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    FaceProvider provider = ctx.getBean(FaceProvider.class);
                    assertThat(provider).isNotInstanceOf(InsightFaceProvider.class)
                            .isNotInstanceOf(FaceProviderDouble.class);
                    ApiException failure = assertThrows(ApiException.class,
                            () -> provider.classify("grant", new byte[]{1}));
                    assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);

                    assertInstanceOf(FailClosedCareFaceVerifier.class, ctx.getBean(CareFaceVerifier.class));
                    FaceIdentityResolver resolver = ctx.getBean(FaceIdentityResolver.class);
                    assertThat(resolver).isNotInstanceOf(UnavailableFaceIdentityResolver.class)
                            .isNotInstanceOf(DevTestFaceIdentityResolver.class);
                    ApiException resolverFailure = assertThrows(ApiException.class,
                            () -> resolver.resolve(new byte[]{1}, FaceClassification.MATCHED));
                    assertThat(resolverFailure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
                });
    }

    @Test
    @DisplayName("provider=insightface 缺必填键 → 拒绝启动只列键名")
    void insightfaceMissingKeysRefuseStartup() {
        runner("local").withPropertyValues("app.env=dev", "app.face.provider=insightface")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("app.face.insightface.base-url")
                            .hasMessageContaining("app.face.insightface.namespace")
                            .hasMessageContaining("values are never logged")
                            .hasMessageNotContaining("FAKE-INTERNAL-TOKEN-DO-NOT-USE");
                });
    }

    @Test
    @DisplayName("token 两种来源同时配置 → 拒绝启动（歧义）")
    void tokenSourcesConflictRefusesStartup() {
        runner("local").withPropertyValues("app.env=dev")
                .withPropertyValues("app.face.provider=insightface",
                        "app.face.insightface.base-url=http://10.3.6.163:8010",
                        "app.face.insightface.namespace=openvela-mvp",
                        "app.face.insightface.internal-token=FAKE-INTERNAL-TOKEN-DO-NOT-USE",
                        "app.face.insightface.internal-token-file=/nonexistent/fake.token")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("exactly one of internal-token / internal-token-file");
                });
    }

    @Test
    @DisplayName("生产信号 + mode=doubles → 既有守卫仍早期拒绝，未被本轮绕过")
    void productionSignalStillRejected() {
        new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, TestDoubleProvidersConfig.class,
                        IdentityProvidersConfig.class, MemberBindingFaceDouble.class,
                        FailClosedCareFaceVerifier.class, DisabledProvidersConfig.class,
                        DisabledFaceIdentityResolverConfig.class, FaceProvidersConfig.class,
                        AliyunFaceBoundaryConfig.class, ProvidersModeProductionGuard.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles("prod"))
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles")
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure()
                        .isInstanceOf(IllegalStateException.class)
                        .hasMessageContaining("app.providers.mode=doubles is not allowed"));
    }
}

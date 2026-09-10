package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.DeviceCredentialProvider;
import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.media.MediaAccessPolicy;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.FaceProviderDouble;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import cn.yuanxin.mvp.web.testdouble.SmsCodeDouble;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.SimpleTransactionStatus;

import java.io.InputStream;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 生产 fail closed（decisions #7）：app.env=production 时只有替身/缺实现
 * → 启动失败；提供真实实现 → 启动成功。并锁定（oracle round-2 R2-6）：
 * 媒体授权拒绝在<b>无条件</b> validator 内，存在自定义 @Primary
 * MediaAccessPolicy 也不会被跳过；dev 下自定义 @Primary 策略确实生效。
 * 不依赖 PG/MVC（纯上下文 runner）。
 */
class ProductionFailClosedTest {

    @Configuration
    @EnableConfigurationProperties(AppProperties.class)
    static class ValidatorConfig {
        @Bean
        ProductionFailClosedValidator validator(org.springframework.context.ApplicationContext ctx,
                                                AppProperties props) {
            return new ProductionFailClosedValidator(ctx, props);
        }
    }

    @Configuration
    static class DoublesOnlyConfig {
        @Bean
        SessionProvider sessionProvider() {
            return new InMemorySessionDouble();
        }

        @Bean
        SmsCodeProvider smsCodeProvider() {
            return new SmsCodeDouble("123456");
        }

        @Bean
        FaceProvider faceProvider() {
            return new FaceProviderDouble("MATCHED");
        }

        @Bean
        StoragePort storagePort() {
            return new FileSystemStorageDouble("/tmp/mvp-a-failclosed-unused");
        }

        @Bean
        DeviceCredentialProvider deviceCredentialProvider() {
            return (credential, credentialVersion, proof) -> Optional.empty();
        }
    }

    @Configuration
    static class RealProvidersConfig {
        @Bean
        SessionProvider sessionProvider() {
            return new SessionProvider() {
                @Override
                public Optional<AuthenticatedPrincipal> authenticate(String accessToken) {
                    return Optional.empty();
                }

                @Override
                public IssuedAppSession createAppSession(UUID accountId, String installationId,
                                                         long authRevision) {
                    throw new UnsupportedOperationException();
                }

                @Override
                public Optional<IssuedAppSession> refreshAppSession(String refreshCredential) {
                    return Optional.empty();
                }

                @Override
                public Optional<RevokedSession> revokeSession(String accessToken) {
                    return Optional.empty();
                }

                @Override
                public IssuedGimbalSession createGimbalSession(UUID gimbalId, long credentialVersion) {
                    throw new UnsupportedOperationException();
                }
            };
        }

        @Bean
        SmsCodeProvider smsCodeProvider() {
            return new SmsCodeProvider() {
                @Override
                public ChallengeOutcome issue(String phone, String purpose) {
                    return new ChallengeOutcome("real", 60);
                }

                @Override
                public Optional<String> verify(String challengeId, String code) {
                    return Optional.empty();
                }
            };
        }

        @Bean
        DeviceCredentialProvider deviceCredentialProvider() {
            return (credential, credentialVersion, proof) -> Optional.empty();
        }

        @Bean
        FaceProvider faceProvider() {
            return (purpose, content) -> FaceClassification.DEPENDENCY_FAILED;
        }

        @Bean
        StoragePort storagePort() {
            return new StoragePort() {
                @Override
                public void put(String objectKey, InputStream content, long byteSize,
                                String contentType) {
                }

                @Override
                public InputStream getStream(String objectKey) {
                    return null;
                }

                @Override
                public byte[] get(String objectKey) {
                    return new byte[0];
                }

                @Override
                public boolean exists(String objectKey) {
                    return false;
                }

                @Override
                public void delete(String objectKey) {
                }
            };
        }
    }

    @Test
    @DisplayName("prod：只有测试替身 → 启动失败（fail closed）")
    void doublesOnlyFailsInProduction() {
        new ApplicationContextRunner()
                .withPropertyValues("app.env=production")
                .withUserConfiguration(ValidatorConfig.class, DoublesOnlyConfig.class)
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("prod：缺实现同样失败；真实实现齐备则通过")
    void missingProvidersFailRealOnesPass() {
        new ApplicationContextRunner()
                .withPropertyValues("app.env=production")
                .withUserConfiguration(ValidatorConfig.class)
                .run(ctx -> assertThat(ctx).hasFailed());
        new ApplicationContextRunner()
                .withPropertyValues("app.env=production")
                .withUserConfiguration(ValidatorConfig.class, RealProvidersConfig.class)
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }

    @Configuration
    static class CustomPrimaryPolicyConfig {
        @Bean
        @Primary
        MediaAccessPolicy customPrimaryPolicy() {
            return (principal, media) -> true;
        }
    }

    @Configuration
    static class FoundationDepsConfig {
        @Bean
        PlatformTransactionManager txManager() {
            return new PlatformTransactionManager() {
                @Override
                public TransactionStatus getTransaction(TransactionDefinition definition) {
                    return new SimpleTransactionStatus();
                }

                @Override
                public void commit(TransactionStatus status) {
                }

                @Override
                public void rollback(TransactionStatus status) {
                }
            };
        }

        @Bean
        cn.yuanxin.mvp.web.auth.PrincipalContextArgumentResolver principalContextArgumentResolver() {
            return new cn.yuanxin.mvp.web.auth.PrincipalContextArgumentResolver();
        }
    }

    @Test
    @DisplayName("R2-6a：自定义 @Primary 策略 + production + allow-any=true → 仍启动失败（validator 无条件）")
    void productionRefusesOpenMediaEvenWithCustomPolicy() {
        new ApplicationContextRunner()
                .withPropertyValues("app.env=production", "app.media.allow-any-authenticated=true")
                .withUserConfiguration(ValidatorConfig.class, RealProvidersConfig.class,
                        CustomPrimaryPolicyConfig.class)
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("production fail-closed"));
    }

    @Test
    @DisplayName("R2-6a：自定义 @Primary 策略 + production + access-mode=owner-dev → 仍启动失败")
    void productionRefusesNonDefaultAccessModeEvenWithCustomPolicy() {
        new ApplicationContextRunner()
                .withPropertyValues("app.env=production", "app.media.access-mode=owner-dev")
                .withUserConfiguration(ValidatorConfig.class, RealProvidersConfig.class,
                        CustomPrimaryPolicyConfig.class)
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure().hasMessageContaining("app.media.access-mode"));
    }

    @Test
    @DisplayName("R2-6b：dev 下自定义 @Primary MediaAccessPolicy 覆盖默认 deny-all（B/C/D 接线生效）")
    void devCustomPrimaryPolicyOverridesDefault() {
        new ApplicationContextRunner()
                .withPropertyValues("app.env=dev")
                .withUserConfiguration(FoundationConfig.class, FoundationDepsConfig.class,
                        CustomPrimaryPolicyConfig.class)
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    // 用户 @Configuration 与 FoundationConfig 无自动配置排序保证，
                    // 默认 bean 可能已注册；解析按 @Primary 取胜（B/C/D 接线约定）。
                    MediaAccessPolicy policy = ctx.getBean(MediaAccessPolicy.class);
                    assertThat(policy.canAccess(null, null)).isTrue();
                    assertThat(policy.getClass().getName()).doesNotContain("DenyAll");
                });
    }
}

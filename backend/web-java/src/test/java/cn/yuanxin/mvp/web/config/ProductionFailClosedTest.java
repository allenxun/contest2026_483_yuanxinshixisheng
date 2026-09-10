package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.DeviceCredentialProvider;
import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.FaceProviderDouble;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import cn.yuanxin.mvp.web.testdouble.SmsCodeDouble;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.io.InputStream;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 生产 fail closed（decisions #7）：app.env=production 时只有替身/缺实现
 * → 启动失败；提供真实实现 → 启动成功。不依赖 PG/MVC（纯上下文 runner）。
 */
class ProductionFailClosedTest {

    @Configuration
    static class ValidatorConfig {
        @Bean
        ProductionFailClosedValidator validator(org.springframework.context.ApplicationContext ctx) {
            return new ProductionFailClosedValidator(ctx);
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
                public IssuedAppSession createAppSession(UUID accountId, String installationId) {
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
}

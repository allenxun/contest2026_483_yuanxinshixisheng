package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.auth.DeviceCredentialProvider;
import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.media.StoragePort;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import java.io.InputStream;
import java.util.Optional;
import java.util.UUID;

/**
 * 显式禁用某能力时的占位接线（app.providers.mode=disabled）：
 * 所有依赖该能力的端点运行时返回 503 DEPENDENCY_UNAVAILABLE 信封
 * （fail closed——绝不降级成"默认通过"或假成功）。
 */
@Configuration
@ConditionalOnProperty(name = "app.providers.mode", havingValue = "disabled")
public class DisabledProvidersConfig {

    private static ApiException disabled(String capability) {
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "capability disabled by configuration: " + capability);
    }

    @Bean
    public SessionProvider sessionProvider() {
        return new SessionProvider() {
            @Override
            public Optional<cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal> authenticate(String accessToken) {
                throw disabled("session");
            }

            @Override
            public IssuedAppSession createAppSession(UUID accountId, String installationId,
                                                     long authRevision) {
                throw disabled("session");
            }

            @Override
            public Optional<IssuedAppSession> refreshAppSession(String refreshCredential) {
                throw disabled("session");
            }

            @Override
            public Optional<RevokedSession> revokeSession(String accessToken) {
                throw disabled("session");
            }

            @Override
            public IssuedGimbalSession createGimbalSession(UUID gimbalId, long credentialVersion) {
                throw disabled("session");
            }
        };
    }

    @Bean
    public SmsCodeProvider smsCodeProvider() {
        return new SmsCodeProvider() {
            @Override
            public ChallengeOutcome issue(String phone, String purpose) {
                throw disabled("sms");
            }

            @Override
            public Optional<String> verify(String challengeId, String code) {
                throw disabled("sms");
            }
        };
    }

    @Bean
    public DeviceCredentialProvider deviceCredentialProvider() {
        return (credential, credentialVersion, proof) -> {
            throw disabled("device-credential");
        };
    }

    @Bean
    public FaceProvider faceProvider() {
        return (purpose, content) -> {
            throw disabled("face");
        };
    }

    @Bean
    public StoragePort storagePort() {
        return new StoragePort() {
            @Override
            public void put(String objectKey, InputStream content, long byteSize, String contentType) {
                throw disabled("storage");
            }

            @Override
            public InputStream getStream(String objectKey) {
                throw disabled("storage");
            }

            @Override
            public byte[] get(String objectKey) {
                throw disabled("storage");
            }

            @Override
            public boolean exists(String objectKey) {
                throw disabled("storage");
            }

            @Override
            public void delete(String objectKey) {
                throw disabled("storage");
            }
        };
    }
}

package cn.yuanxin.mvp.web.auth;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * M2-A01 云台设备会话（同时是 27 业务编号与 x-foundation 基础协议，
 * contracts decisions-notes §8；A 包实现，不打 501）。
 *
 * <p>设备凭据 → DeviceCredentialProvider 验证 → 绑定 gimbalId +
 * credentialVersion + 会话 ID 签发票据。凭据失败统一 401 AUTH_REQUIRED
 * （不区分“未知凭据”“版本不符”，避免枚举探测——A 裁量，已记 README）。
 * 不使用 Idempotency-Key 缓存可重放的秘密凭据。</p>
 */
@RestController
@RequestMapping("/api/v1")
public class GimbalSessionController {

    private final DeviceCredentialProvider deviceCredentialProvider;
    private final SessionProvider sessionProvider;
    private final EnvelopeSupport envelopes;

    public GimbalSessionController(DeviceCredentialProvider deviceCredentialProvider,
                                   SessionProvider sessionProvider, EnvelopeSupport envelopes) {
        this.deviceCredentialProvider = deviceCredentialProvider;
        this.sessionProvider = sessionProvider;
        this.envelopes = envelopes;
    }

    public record GimbalSessionRequestBody(
            @NotBlank @Size(max = 256) String credential,
            @NotBlank @Pattern(regexp = "^(0|[1-9][0-9]*)$",
                    message = "credentialVersion must be a decimal bigint string") String credentialVersion,
            @NotBlank @Size(max = 512) String proof) {
    }

    public record GimbalSessionData(String gimbalId, String sessionToken, String expiresAt,
                                    String serverTime) {
    }

    @PostMapping("/gimbal-sessions")
    public SuccessEnvelope createGimbalSession(@Valid @RequestBody GimbalSessionRequestBody body,
                                               HttpServletRequest request) {
        long version;
        try {
            version = Long.parseLong(body.credentialVersion());
        } catch (NumberFormatException e) {
            throw new ApiException(ErrorCode.INVALID_INPUT,
                    "credentialVersion out of bigint range");
        }
        DeviceCredentialProvider.GimbalIdentity identity =
                deviceCredentialProvider.verify(body.credential(), version, body.proof())
                        .orElseThrow(() -> new ApiException(ErrorCode.AUTH_REQUIRED,
                                "device credential not verified"));
        SessionProvider.IssuedGimbalSession session = sessionProvider.createGimbalSession(
                identity.gimbalId(), identity.credentialVersion());
        return envelopes.ok(request, new GimbalSessionData(
                session.gimbalId().toString(), session.sessionToken(),
                EnvelopeSupport.rfc3339(session.expiresAt()),
                EnvelopeSupport.rfc3339(java.time.Instant.now())));
    }
}

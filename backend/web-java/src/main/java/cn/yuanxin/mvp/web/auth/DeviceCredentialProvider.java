package cn.yuanxin.mvp.web.auth;

import java.util.Optional;
import java.util.UUID;

/**
 * 云台设备凭据验证端口（DD 4.2；M2-A01）。
 * 验证设备凭据 → 可信云台身份（gimbalId + 当前 credential_version）。
 * 验证失败绝不登记为可信在线（fail closed）。
 */
public interface DeviceCredentialProvider {

    Optional<GimbalIdentity> verify(String credential, long credentialVersion, String proof);

    record GimbalIdentity(UUID gimbalId, String serialNo, long credentialVersion) {
    }
}

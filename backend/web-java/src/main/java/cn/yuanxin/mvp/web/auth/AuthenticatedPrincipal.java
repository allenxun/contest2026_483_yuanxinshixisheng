package cn.yuanxin.mvp.web.auth;

import java.time.Instant;
import java.util.UUID;

/**
 * 会话提供方认证通过后返回的主体快照（服务端派生，绝不来自请求体声明）。
 * APP 会话填 accountUuid/installationId；GIMBAL 会话填 gimbalUuid/credentialVersion。
 */
public record AuthenticatedPrincipal(
        PrincipalType principalType,
        UUID accountUuid,
        String installationId,
        UUID gimbalUuid,
        long credentialVersion,
        String sessionId) {

    public static AuthenticatedPrincipal app(UUID accountUuid, String installationId, String sessionId) {
        return new AuthenticatedPrincipal(PrincipalType.APP, accountUuid, installationId, null, 0, sessionId);
    }

    public static AuthenticatedPrincipal gimbal(UUID gimbalUuid, long credentialVersion, String sessionId) {
        return new AuthenticatedPrincipal(PrincipalType.GIMBAL, null, null, gimbalUuid, credentialVersion, sessionId);
    }
}

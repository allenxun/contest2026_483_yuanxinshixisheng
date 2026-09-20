package cn.yuanxin.mvp.web.auth;

import java.time.Instant;
import java.util.UUID;

/**
 * 会话提供方认证通过后返回的主体快照（服务端派生，绝不来自请求体声明）。
 * APP 会话填 accountUuid/installationId/authRevision（签发时刻 accounts.auth_revision）；
 * GIMBAL 会话填 gimbalUuid/credentialVersion（签发时刻 gimbals.credential_version）。
 *
 * <p>BearerAuthFilter 每次请求按快照与本地 T14/T03 行复核（PrincipalRevalidator）：
 * 账号 disabled、auth_revision 递增（全端登出）、credential_version 轮换都会让
 * 旧 token 立即 401 SESSION_INVALID——提供方快照不是充分认证依据（oracle B2）。</p>
 */
public record AuthenticatedPrincipal(
        PrincipalType principalType,
        UUID accountUuid,
        String installationId,
        UUID gimbalUuid,
        long credentialVersion,
        String sessionId,
        long authRevision) {

    public static AuthenticatedPrincipal app(UUID accountUuid, String installationId,
                                             String sessionId, long authRevision) {
        return new AuthenticatedPrincipal(PrincipalType.APP, accountUuid, installationId,
                null, 0, sessionId, authRevision);
    }

    public static AuthenticatedPrincipal gimbal(UUID gimbalUuid, long credentialVersion, String sessionId) {
        return new AuthenticatedPrincipal(PrincipalType.GIMBAL, null, null, gimbalUuid,
                credentialVersion, sessionId, 0);
    }
}

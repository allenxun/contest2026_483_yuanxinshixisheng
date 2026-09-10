package cn.yuanxin.mvp.web.auth;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/**
 * APP/GIMBAL 会话提供方适配端口（DD 4.1/4.2；digest §6）。
 *
 * <p>会话存储表不存在于 14 表设计（不擅自加表）——真实实现由未来选定的
 * 认证提供方承担；dev/test 使用内存隔离替身 {@code InMemorySessionDouble}。</p>
 *
 * <p>核心安全约束：{@link #authenticate(String)} 只接受本提供方自己签发的
 * token；任意字符串（包括猜测的 accountId/installationId）绝不认证成功。</p>
 */
public interface SessionProvider {

    /** token → 主体快照（须含签发时刻的 accounts.auth_revision /
     *  gimbals.credential_version，服务端每请求与本地行复核）；非本提供方签发/
     *  已撤销/过期 → empty。 */
    Optional<AuthenticatedPrincipal> authenticate(String accessToken);

    /**
     * 手机号会话签发（challenge+code 验证并 find-or-create 本地账号后调用）。
     * authRevision = 调用方刚读取的 accounts.auth_revision 快照：账号 disabled 由
     * 调用方（AuthController）先行拒绝；后续 revision 递增即令本会话失效。
     */
    IssuedAppSession createAppSession(UUID accountId, String installationId, long authRevision);

    /** 刷新：旧凭据换新凭据（轮换与旧凭据撤销由提供方协议保证）。
     *  本地账号已 disabled 时必须返回 empty（替身直读 T14 行）。 */
    Optional<IssuedAppSession> refreshAppSession(String refreshCredential);

    /** 撤销当前会话（退出登录）。返回被撤销会话的主体信息供 T09 失效。 */
    Optional<RevokedSession> revokeSession(String accessToken);

    /** 云台设备会话签发（M2-A01；DeviceCredentialProvider 验证通过后调用）。 */
    IssuedGimbalSession createGimbalSession(UUID gimbalId, long credentialVersion);

    record IssuedAppSession(String accessToken, String refreshToken, UUID accountId,
                            String installationId, Instant expiresAt) {
    }

    record IssuedGimbalSession(String sessionToken, UUID gimbalId, long credentialVersion,
                               Instant expiresAt) {
    }

    /** sessionId 同时作为 T09 notification_destinations.session_ref 的匹配值。 */
    record RevokedSession(UUID accountId, String installationId, String sessionId) {
    }
}

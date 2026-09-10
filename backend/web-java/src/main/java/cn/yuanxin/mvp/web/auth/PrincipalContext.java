package cn.yuanxin.mvp.web.auth;

import java.util.UUID;

/**
 * 请求内认证主体上下文（ARCH 6.1；digest §6）。
 *
 * <p>身份只由服务端会话（token）派生——请求体声明的 accountId/gimbalId
 * 一律不作为认证依据（fail closed 规则）。APP 主体填 accountUuid +
 * installationId + sessionId；GIMBAL 主体填 gimbalUuid + credentialVersion +
 * sessionId。credentialVersion 为 DB bigint，Java 内以 long 表示，出 JSON
 * 时按契约转十进制字符串。</p>
 *
 * <p>控制器通过 {@link PrincipalContextArgumentResolver} 以方法参数注入
 * （由 BearerAuthFilter 在认证成功时写入 request 属性）。</p>
 */
public record PrincipalContext(
        PrincipalType principalType,
        UUID accountUuid,
        String installationId,
        UUID gimbalUuid,
        long credentialVersion,
        String sessionId,
        String requestId) {

    public static PrincipalContext forApp(AuthenticatedPrincipal p, String requestId) {
        return new PrincipalContext(PrincipalType.APP, p.accountUuid(), p.installationId(),
                null, 0, p.sessionId(), requestId);
    }

    public static PrincipalContext forGimbal(AuthenticatedPrincipal p, String requestId) {
        return new PrincipalContext(PrincipalType.GIMBAL, null, null,
                p.gimbalUuid(), p.credentialVersion(), p.sessionId(), requestId);
    }

    /**
     * T13 principal_id 规范文本（contracts/decisions-notes.md §2；A/decisions #2）：
     * app_account = "&lt;account_uuid&gt;:&lt;installation_id&gt;"；gimbal = "&lt;gimbal_uuid&gt;"。
     */
    public String t13PrincipalId() {
        return switch (principalType) {
            case APP -> accountUuid + ":" + installationId;
            case GIMBAL -> String.valueOf(gimbalUuid);
        };
    }

    /** T13 principal_type 列取值。 */
    public String t13PrincipalType() {
        return switch (principalType) {
            case APP -> "app_account";
            case GIMBAL -> "gimbal";
        };
    }
}

package cn.yuanxin.mvp.web.auth;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * 每请求本地状态复核（oracle B2）：提供方 authenticate() 的快照<b>不是</b>
 * 充分认证依据——会话签发后账号可能被停用、auth_revision 可能递增（全端
 * 登出）、云台 credential_version 可能轮换。每请求最多一条单行查询
 * （无 JOIN、无锁）与快照比对：
 *
 * <ul>
 *   <li>APP：accounts.status 必须 'active' 且 auth_revision == 签发快照；</li>
 *   <li>GIMBAL：gimbals.credential_version == 会话快照（行缺失同样失效）。</li>
 * </ul>
 *
 * <p>不匹配 → 由 BearerAuthFilter 统一 401 SESSION_INVALID 信封。真实提供方
 * （B/C/D 后）接入后此复核仍必须执行：它守的是本库状态，不依赖提供方语义。</p>
 */
@Component
public class PrincipalRevalidator {

    private final JdbcTemplate jdbc;

    public PrincipalRevalidator(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** true = 快照与本地状态仍一致（认证有效）。 */
    public boolean stillValid(AuthenticatedPrincipal p) {
        return switch (p.principalType()) {
            case APP -> {
                var rows = jdbc.query(
                        "SELECT status, auth_revision FROM accounts WHERE id = ?",
                        (rs, i) -> new Object[]{rs.getString("status"), rs.getLong("auth_revision")},
                        p.accountUuid());
                yield !rows.isEmpty()
                        && "active".equals(rows.get(0)[0])
                        && ((Long) rows.get(0)[1]).longValue() == p.authRevision();
            }
            case GIMBAL -> {
                var rows = jdbc.query(
                        "SELECT credential_version FROM gimbals WHERE id = ?",
                        (rs, i) -> rs.getLong("credential_version"),
                        p.gimbalUuid());
                yield !rows.isEmpty() && rows.get(0) == p.credentialVersion();
            }
        };
    }
}

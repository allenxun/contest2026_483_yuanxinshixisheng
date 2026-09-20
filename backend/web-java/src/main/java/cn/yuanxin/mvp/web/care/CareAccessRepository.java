package cn.yuanxin.mvp.web.care;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.UUID;

/** T02 member_access_grants 只读存在性检查（单表，status='active'）。 */
@Repository
public class CareAccessRepository {

    private final JdbcTemplate jdbc;

    public CareAccessRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 当前账号对该成员是否存在 active 授权。 */
    public boolean hasActiveGrant(UUID accountId, UUID memberId) {
        if (accountId == null || memberId == null) {
            return false;
        }
        return !jdbc.query("SELECT 1 FROM member_access_grants"
                        + " WHERE account_id = ? AND member_id = ? AND status = 'active' LIMIT 1",
                (rs, i) -> Boolean.TRUE, accountId, memberId).isEmpty();
    }

    /**
     * 最终短事务锁序 T02：{@code SELECT 1 ... FOR UPDATE}（锁内复核授权仍 active；
     * 与撤销交错时以锁内结果为准）。
     */
    public boolean hasActiveGrantForUpdate(UUID accountId, UUID memberId) {
        if (accountId == null || memberId == null) {
            return false;
        }
        return !jdbc.query("SELECT 1 FROM member_access_grants"
                        + " WHERE account_id = ? AND member_id = ? AND status = 'active'"
                        + " LIMIT 1 FOR UPDATE",
                (rs, i) -> Boolean.TRUE, accountId, memberId).isEmpty();
    }
}

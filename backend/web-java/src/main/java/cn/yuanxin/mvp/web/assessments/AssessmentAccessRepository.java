package cn.yuanxin.mvp.web.assessments;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

/**
 * 授权/方案/执行只读单表查询（每方法一条单表 SELECT，无 JOIN）：
 * T02 active 查看权、T06 方案生成状态、T07 未收尾云台执行。
 */
@Repository
public class AssessmentAccessRepository {

    private final JdbcTemplate jdbc;

    public AssessmentAccessRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record OpenExecution(UUID id, String status) {
    }

    public boolean hasActiveGrant(UUID accountId, UUID memberId) {
        var rows = jdbc.queryForList(
                "SELECT 1 FROM member_access_grants"
                        + " WHERE account_id = ? AND member_id = ? AND status = 'active' LIMIT 1",
                Integer.class, accountId, memberId);
        return !rows.isEmpty();
    }

    public Optional<String> planStatusByAssessmentId(UUID assessmentId) {
        var rows = jdbc.queryForList(
                "SELECT generation_status FROM care_plans WHERE assessment_id = ? LIMIT 1",
                String.class, assessmentId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public Optional<OpenExecution> findOpenByGimbal(UUID gimbalId) {
        var rows = jdbc.query(
                "SELECT id, status FROM care_executions"
                        + " WHERE controller_gimbal_id = ? AND closed_at IS NULL LIMIT 1",
                (rs, i) -> new OpenExecution(rs.getObject("id", UUID.class), rs.getString("status")),
                gimbalId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }
}

package cn.yuanxin.mvp.web.care;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** T05 skin_assessments 只读（按 report_id 定位 id + member_id；单表）。 */
@Repository
public class AssessmentReadRepository {

    private final JdbcTemplate jdbc;

    public AssessmentReadRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record AssessmentRef(UUID id, UUID memberId) {
    }

    public Optional<AssessmentRef> findByReportId(UUID reportId) {
        List<AssessmentRef> rows = jdbc.query(
                "SELECT id, member_id FROM skin_assessments WHERE report_id = ?",
                (rs, i) -> new AssessmentRef(rs.getObject("id", UUID.class),
                        rs.getObject("member_id", UUID.class)),
                reportId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }
}

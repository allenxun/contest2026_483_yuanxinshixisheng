package cn.yuanxin.mvp.web.assessments;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

/** T03 gimbals 单表显式 SQL（D 包只读写当前任务指针列）。 */
@Repository
public class AssessmentGimbalRepository {

    private final JdbcTemplate jdbc;

    public AssessmentGimbalRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Pointer(UUID id, UUID currentAssessmentId, long currentAssessmentRevision) {
    }

    private static final String POINTER_COLUMNS =
            "SELECT id, current_assessment_id, current_assessment_revision FROM gimbals";

    private static Pointer map(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new Pointer(
                rs.getObject("id", UUID.class),
                rs.getObject("current_assessment_id", UUID.class),
                rs.getLong("current_assessment_revision"));
    }

    public Optional<Pointer> lockById(UUID gimbalId) {
        var rows = jdbc.query(POINTER_COLUMNS + " WHERE id = ? FOR UPDATE",
                (rs, i) -> map(rs), gimbalId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public Optional<Pointer> findById(UUID gimbalId) {
        var rows = jdbc.query(POINTER_COLUMNS + " WHERE id = ?",
                (rs, i) -> map(rs), gimbalId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /** 原子换指针 + 代次 +1（字段级 UPDATE）。 */
    public int setCurrentAssessment(UUID gimbalId, UUID taskId) {
        return jdbc.update("UPDATE gimbals SET current_assessment_id = ?,"
                        + " current_assessment_revision = current_assessment_revision + 1,"
                        + " updated_at = now() WHERE id = ?",
                taskId, gimbalId);
    }
}

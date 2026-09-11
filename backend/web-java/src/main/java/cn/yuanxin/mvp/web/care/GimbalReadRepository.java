package cn.yuanxin.mvp.web.care;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** T03 gimbals 只读指针（current_assessment_id / credential 列；单表）。 */
@Repository
public class GimbalReadRepository {

    private final JdbcTemplate jdbc;

    public GimbalReadRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record GimbalPointer(UUID gimbalId, UUID currentAssessmentId,
                                long currentAssessmentRevision, long credentialVersion) {
    }

    public Optional<GimbalPointer> findPointer(UUID gimbalId) {
        List<GimbalPointer> rows = jdbc.query(
                "SELECT id, current_assessment_id, current_assessment_revision, credential_version"
                        + " FROM gimbals WHERE id = ?",
                (rs, i) -> new GimbalPointer(
                        rs.getObject("id", UUID.class),
                        rs.getObject("current_assessment_id", UUID.class),
                        rs.getLong("current_assessment_revision"),
                        rs.getLong("credential_version")),
                gimbalId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /** 最终短事务锁序 T03：{@code SELECT ... FOR UPDATE}（锁内复核当前任务/代次）。 */
    public Optional<GimbalPointer> lockById(UUID gimbalId) {
        List<GimbalPointer> rows = jdbc.query(
                "SELECT id, current_assessment_id, current_assessment_revision, credential_version"
                        + " FROM gimbals WHERE id = ? FOR UPDATE",
                (rs, i) -> new GimbalPointer(
                        rs.getObject("id", UUID.class),
                        rs.getObject("current_assessment_id", UUID.class),
                        rs.getLong("current_assessment_revision"),
                        rs.getLong("credential_version")),
                gimbalId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }
}

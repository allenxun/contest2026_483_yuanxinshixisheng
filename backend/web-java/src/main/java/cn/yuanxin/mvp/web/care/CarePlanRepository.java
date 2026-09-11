package cn.yuanxin.mvp.web.care;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * T06 care_plans 只读单表仓储（显式列名，无 JOIN/无关联子查询）。
 *
 * <p>{@link CarePlanRow} 覆盖 Stage 2/3 所需全部列，避免后续返工；JSONB 列
 * 一律 {@code ::text} 取出后在投影层按字段规则映射。</p>
 */
@Repository
public class CarePlanRepository {

    private final JdbcTemplate jdbc;

    public CarePlanRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record CarePlanRow(
            UUID id,
            UUID assessmentId,
            UUID memberId,
            String generationStatus,
            Long inputPhotoVersion,
            long generationRevision,
            String inputSnapshot,
            String planSummary,
            String planPayload,
            Long targetCount,
            long completedCount,
            Instant completedAt,
            long progressRevision,
            String failureDetail,
            Instant createdAt,
            Instant updatedAt) {
    }

    private static final String COLUMNS = "id, assessment_id, member_id, generation_status,"
            + " input_photo_version, generation_revision, input_snapshot::text AS input_snapshot,"
            + " plan_summary::text AS plan_summary, plan_payload::text AS plan_payload,"
            + " target_count, completed_count, completed_at, progress_revision,"
            + " failure_detail::text AS failure_detail, created_at, updated_at";

    private static final RowMapper<CarePlanRow> MAPPER = (rs, i) -> new CarePlanRow(
            rs.getObject("id", UUID.class),
            rs.getObject("assessment_id", UUID.class),
            rs.getObject("member_id", UUID.class),
            rs.getString("generation_status"),
            rs.getObject("input_photo_version", Long.class),
            rs.getLong("generation_revision"),
            rs.getString("input_snapshot"),
            rs.getString("plan_summary"),
            rs.getString("plan_payload"),
            rs.getObject("target_count", Long.class),
            rs.getLong("completed_count"),
            rs.getTimestamp("completed_at") == null ? null : rs.getTimestamp("completed_at").toInstant(),
            rs.getLong("progress_revision"),
            rs.getString("failure_detail"),
            rs.getTimestamp("created_at").toInstant(),
            rs.getTimestamp("updated_at").toInstant());

    public Optional<CarePlanRow> findById(UUID planId) {
        List<CarePlanRow> rows = jdbc.query(
                "SELECT " + COLUMNS + " FROM care_plans WHERE id = ?", MAPPER, planId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /** 按 assessment_id 单表定位（M4-A03 云台由当前任务解析方案）。 */
    public Optional<CarePlanRow> findByAssessmentId(UUID assessmentId) {
        List<CarePlanRow> rows = jdbc.query(
                "SELECT " + COLUMNS + " FROM care_plans WHERE assessment_id = ?", MAPPER, assessmentId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /** 最终短事务锁序 T06：{@code SELECT ... FOR UPDATE}（锁内复核 ready/K<N）。 */
    public Optional<CarePlanRow> lockById(UUID planId) {
        List<CarePlanRow> rows = jdbc.query(
                "SELECT " + COLUMNS + " FROM care_plans WHERE id = ? FOR UPDATE", MAPPER, planId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /**
     * M4-A05 次数账本汇总：increase completed_count by delta、progress_revision+1、
     * 首次达标写 completed_at；仅 ready 方案可入账（0 行由调用方转 INTERNAL）。
     */
    public int addCompletedCount(UUID planId, long delta, Instant receivedAt) {
        return jdbc.update("UPDATE care_plans SET completed_count = completed_count + ?,"
                        + " progress_revision = progress_revision + 1,"
                        + " completed_at = CASE WHEN completed_at IS NULL"
                        + "   AND completed_count + ? >= target_count THEN ? ELSE completed_at END,"
                        + " updated_at = ? WHERE id = ? AND generation_status = 'ready'",
                delta, delta, Timestamp.from(receivedAt), Timestamp.from(receivedAt), planId);
    }

    /**
     * 按成员（可选评估）键集分页：created_at DESC, id DESC。
     *
     * @param assessmentId 可空；非空时附加 {@code AND assessment_id = ?}
     * @param afterCreatedAt 可空游标排序值（第一页 null，省略游标谓词）
     * @param afterId        可空游标末位 ID
     * @param fetchSize     取 limit+1 以判断 nextCursor
     */
    public List<CarePlanRow> pageByMember(UUID memberId, UUID assessmentId,
                                          Instant afterCreatedAt, UUID afterId, int fetchSize) {
        StringBuilder sql = new StringBuilder("SELECT ").append(COLUMNS)
                .append(" FROM care_plans WHERE member_id = ?");
        java.util.List<Object> args = new java.util.ArrayList<>();
        args.add(memberId);
        if (assessmentId != null) {
            sql.append(" AND assessment_id = ?");
            args.add(assessmentId);
        }
        if (afterCreatedAt != null && afterId != null) {
            sql.append(" AND (created_at, id) < (?, ?)");
            args.add(Timestamp.from(afterCreatedAt));
            args.add(afterId);
        }
        sql.append(" ORDER BY created_at DESC, id DESC LIMIT ?");
        args.add(fetchSize);
        return jdbc.query(sql.toString(), MAPPER, args.toArray());
    }
}

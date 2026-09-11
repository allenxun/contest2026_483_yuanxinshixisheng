package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * T07 care_executions 只读单表仓储（显式列名，无 JOIN/无关联子查询）。
 *
 * <p>{@link CareExecutionRow} 覆盖 Stage 2/3 所需全部列（控制端归属、核验
 * 代次、观测流、账本、收尾清单等）。</p>
 */
@Repository
public class CareExecutionRepository {

    private final JdbcTemplate jdbc;

    public CareExecutionRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record CareExecutionRow(
            UUID id,
            UUID planId,
            UUID memberId,
            UUID microcrystalId,
            String controllerType,
            UUID controllerAccountId,
            String controllerInstallationId,
            UUID controllerGimbalId,
            UUID assessmentIdAtStart,
            String planSnapshot,
            String status,
            long verificationRevision,
            Instant lastVerifiedAt,
            String latestVerification,
            String observationEpoch,
            Long lastObservationSeq,
            String latestObservation,
            long acceptedCount,
            String closureManifest,
            Instant stoppedAt,
            Instant closedAt,
            UUID sourceRequestId,
            Instant createdAt,
            Instant updatedAt) {
    }

    private static final String COLUMNS = "id, plan_id, member_id, microcrystal_id,"
            + " controller_type, controller_account_id, controller_installation_id,"
            + " controller_gimbal_id, assessment_id_at_start, plan_snapshot::text AS plan_snapshot,"
            + " status, verification_revision, last_verified_at,"
            + " latest_verification::text AS latest_verification,"
            + " observation_epoch, last_observation_seq,"
            + " latest_observation::text AS latest_observation, accepted_count,"
            + " closure_manifest::text AS closure_manifest, stopped_at, closed_at,"
            + " source_request_id, created_at, updated_at";

    private static final RowMapper<CareExecutionRow> MAPPER = (rs, i) -> new CareExecutionRow(
            rs.getObject("id", UUID.class),
            rs.getObject("plan_id", UUID.class),
            rs.getObject("member_id", UUID.class),
            rs.getObject("microcrystal_id", UUID.class),
            rs.getString("controller_type"),
            rs.getObject("controller_account_id", UUID.class),
            rs.getString("controller_installation_id"),
            rs.getObject("controller_gimbal_id", UUID.class),
            rs.getObject("assessment_id_at_start", UUID.class),
            rs.getString("plan_snapshot"),
            rs.getString("status"),
            rs.getLong("verification_revision"),
            rs.getTimestamp("last_verified_at") == null ? null : rs.getTimestamp("last_verified_at").toInstant(),
            rs.getString("latest_verification"),
            rs.getString("observation_epoch"),
            rs.getObject("last_observation_seq", Long.class),
            rs.getString("latest_observation"),
            rs.getLong("accepted_count"),
            rs.getString("closure_manifest"),
            rs.getTimestamp("stopped_at") == null ? null : rs.getTimestamp("stopped_at").toInstant(),
            rs.getTimestamp("closed_at") == null ? null : rs.getTimestamp("closed_at").toInstant(),
            rs.getObject("source_request_id", UUID.class),
            rs.getTimestamp("created_at").toInstant(),
            rs.getTimestamp("updated_at").toInstant());

    public Optional<CareExecutionRow> findById(UUID executionId) {
        List<CareExecutionRow> rows = jdbc.query(
                "SELECT " + COLUMNS + " FROM care_executions WHERE id = ?", MAPPER, executionId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /** 最终短事务锁序 T07：{@code SELECT ... FOR UPDATE}（锁内复核状态/代次/归属）。 */
    public Optional<CareExecutionRow> lockById(UUID executionId) {
        List<CareExecutionRow> rows = jdbc.query(
                "SELECT " + COLUMNS + " FROM care_executions WHERE id = ? FOR UPDATE",
                MAPPER, executionId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /**
     * M4-A03 新执行登记（全列插入；占用由两个部分唯一索引原子裁决，
     * {@code DuplicateKeyException} 由调用方分类为 DEVICE_OCCUPIED）。
     */
    public record NewExecution(
            UUID id,
            UUID planId,
            UUID memberId,
            UUID microcrystalId,
            String controllerType,
            UUID controllerAccountId,
            String controllerInstallationId,
            UUID controllerGimbalId,
            UUID assessmentIdAtStart,
            String planSnapshotJson,
            String latestVerificationJson,
            Instant lastVerifiedAt,
            String observationEpoch,
            UUID sourceRequestId) {
    }

    public void insert(NewExecution e) {
        jdbc.update("INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                        + " controller_type, controller_account_id, controller_installation_id,"
                        + " controller_gimbal_id, assessment_id_at_start, plan_snapshot, status,"
                        + " verification_revision, last_verified_at, latest_verification,"
                        + " observation_epoch, accepted_count, source_request_id)"
                        + " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), 'admitted', 1, ?,"
                        + " CAST(? AS jsonb), ?, 0, ?)",
                e.id(), e.planId(), e.memberId(), e.microcrystalId(),
                e.controllerType(), e.controllerAccountId(), e.controllerInstallationId(),
                e.controllerGimbalId(), e.assessmentIdAtStart(), e.planSnapshotJson(),
                Timestamp.from(e.lastVerifiedAt()), e.latestVerificationJson(),
                e.observationEpoch(), e.sourceRequestId());
    }

    /** M4-A05 账本：字段级增加 accepted_count（closed 执行亦可，不碰 status）。 */
    public int addAcceptedCount(UUID executionId, long delta, Instant updatedAt) {
        return jdbc.update("UPDATE care_executions SET accepted_count = accepted_count + ?,"
                        + " updated_at = ? WHERE id = ?",
                delta, Timestamp.from(updatedAt), executionId);
    }

    /**
     * M4-A05 观察合并：更新顺序水位与最新观察；status 由状态机给出（不允许转移时
     * 传当前值）；stoppedAt 仅首次转入 stopped 时非空（COALESCE 保留旧值）。
     */
    public int updateObservation(UUID executionId, long lastObservationSeq,
                                 String latestObservationJson, String status, Instant stoppedAt,
                                 Instant updatedAt) {
        return jdbc.update("UPDATE care_executions SET last_observation_seq = ?,"
                        + " latest_observation = CAST(? AS jsonb), status = ?,"
                        + " stopped_at = COALESCE(?, stopped_at), updated_at = ? WHERE id = ?",
                lastObservationSeq, latestObservationJson, status,
                stoppedAt == null ? null : Timestamp.from(stoppedAt),
                Timestamp.from(updatedAt), executionId);
    }

    /**
     * M4-A06 收尾：仅当仍为 stopped 时置 closed（并发已关则 0 行→already_closed）。
     * 占用由 closed_at 非空经部分唯一索引自然释放，不删行。
     */
    public int close(UUID executionId, Instant closedAt, String closureManifestJson) {
        return jdbc.update("UPDATE care_executions SET status = 'closed', closed_at = ?,"
                        + " closure_manifest = CAST(? AS jsonb), updated_at = ?"
                        + " WHERE id = ? AND status = 'stopped'",
                Timestamp.from(closedAt), closureManifestJson, Timestamp.from(closedAt), executionId);
    }

    /**
     * 迟到差异留痕（DD 6.4，N1）：对已 closed 执行的 closure_manifest 增量更新
     * {@code late_variance}（累计插入条数、最大来源序号、最近接受时间），
     * 不改 closed_at/status/其余 manifest 字段。仅计入实际新增记录。
     */
    public int applyLateVariance(UUID executionId, long insertedCount, long batchMaxSourceSeq,
                                 Instant receivedAt) {
        return jdbc.update("UPDATE care_executions SET closure_manifest = jsonb_set("
                        + "jsonb_set(COALESCE(closure_manifest, '{}'::jsonb),"
                        + " '{schema_version}', '1'::jsonb, true),"
                        + " '{late_variance}', jsonb_build_object("
                        + "   'late_records_count', COALESCE((closure_manifest->'late_variance'"
                        + "     ->>'late_records_count')::bigint, 0) + ?,"
                        + "   'late_max_source_seq', GREATEST(COALESCE((closure_manifest"
                        + "     ->'late_variance'->>'late_max_source_seq')::bigint, 0), ?)::text,"
                        + "   'last_late_received_at', ?), true), updated_at = ?"
                        + " WHERE id = ? AND status = 'closed'",
                insertedCount, batchMaxSourceSeq, EnvelopeSupport.rfc3339(receivedAt),
                Timestamp.from(receivedAt), executionId);
    }

    /**
     * 按成员键集分页（created_at DESC, id DESC），可选 planId 等值与 created_at
     * [from, to] 过滤；from/to 与游标均作用于 created_at。
     */
    public List<CareExecutionRow> pageByMember(UUID memberId, UUID planId, Instant from, Instant to,
                                               Instant afterCreatedAt, UUID afterId, int fetchSize) {
        StringBuilder sql = new StringBuilder("SELECT ").append(COLUMNS)
                .append(" FROM care_executions WHERE member_id = ?");
        List<Object> args = new ArrayList<>();
        args.add(memberId);
        if (planId != null) {
            sql.append(" AND plan_id = ?");
            args.add(planId);
        }
        if (from != null) {
            sql.append(" AND created_at >= ?");
            args.add(Timestamp.from(from));
        }
        if (to != null) {
            sql.append(" AND created_at <= ?");
            args.add(Timestamp.from(to));
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

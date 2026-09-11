package cn.yuanxin.mvp.web.assessments;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * T05 skin_assessments 单表显式 SQL（D 包写边界：受理/照片版本/输入状态列 +
 * 查询投影）。绝不触碰 worker 独占列（member_id、report_*、identity_result、
 * analyzing/report_ready/needs_retake/failed 转换）。
 */
@Repository
public class AssessmentRepository {

    private final JdbcTemplate jdbc;

    public AssessmentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 受理事务行（FOR UPDATE）：含 Java 可写列与判定所需状态列；不读取诊断列。 */
    public record AcceptanceRow(UUID id, UUID gimbalId, UUID memberId, String status,
                                long currentPhotoVersion, long processingRevision,
                                String photoVersions) {
    }

    /** A03 查询投影（不含 report_payload/report_summary 大载荷；failure_detail 不再读取）。 */
    public record ViewRow(UUID id, UUID gimbalId, UUID memberId, String status,
                          long currentPhotoVersion, String photoVersions, UUID reportId,
                          String failureCode, String identityResult) {
    }

    /** A05 报告行（含冻结载荷）。 */
    public record ReportRow(UUID id, UUID gimbalId, UUID memberId, String status,
                            String reportPayload, Instant reportReadyAt) {
    }

    /** A04 列表行。 */
    public record ReportListRow(UUID id, UUID reportId, Instant reportReadyAt, String reportSummary) {
    }

    public Optional<AcceptanceRow> findByIdForUpdate(UUID id) {
        var rows = jdbc.query("SELECT id, gimbal_id, member_id, status, current_photo_version,"
                        + " processing_revision, photo_versions::text AS photo_versions"
                        + " FROM skin_assessments WHERE id = ? FOR UPDATE",
                (rs, i) -> new AcceptanceRow(
                        rs.getObject("id", UUID.class),
                        rs.getObject("gimbal_id", UUID.class),
                        rs.getObject("member_id", UUID.class),
                        rs.getString("status"),
                        rs.getLong("current_photo_version"),
                        rs.getLong("processing_revision"),
                        rs.getString("photo_versions")),
                id);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public Optional<ViewRow> findById(UUID id) {
        var rows = jdbc.query("SELECT id, gimbal_id, member_id, status, current_photo_version,"
                        + " photo_versions::text AS photo_versions, report_id,"
                        + " failure_code, identity_result::text AS identity_result"
                        + " FROM skin_assessments WHERE id = ?",
                (rs, i) -> new ViewRow(
                        rs.getObject("id", UUID.class),
                        rs.getObject("gimbal_id", UUID.class),
                        rs.getObject("member_id", UUID.class),
                        rs.getString("status"),
                        rs.getLong("current_photo_version"),
                        rs.getString("photo_versions"),
                        rs.getObject("report_id", UUID.class),
                        rs.getString("failure_code"),
                        rs.getString("identity_result")),
                id);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public Optional<ReportRow> findByReportId(UUID reportId) {
        var rows = jdbc.query("SELECT id, gimbal_id, member_id, status, report_ready_at,"
                        + " report_payload::text AS report_payload"
                        + " FROM skin_assessments WHERE report_id = ?",
                (rs, i) -> new ReportRow(
                        rs.getObject("id", UUID.class),
                        rs.getObject("gimbal_id", UUID.class),
                        rs.getObject("member_id", UUID.class),
                        rs.getString("status"),
                        rs.getString("report_payload"),
                        rs.getTimestamp("report_ready_at") == null ? null
                                : rs.getTimestamp("report_ready_at").toInstant()),
                reportId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public void insertQueued(UUID id, UUID gimbalId, String photoVersionsJson, UUID t13RequestId) {
        // 不触碰 worker 独占列：member_id 留 NULL、identity_result 用列默认 '{}'
        jdbc.update("INSERT INTO skin_assessments (id, gimbal_id, status,"
                        + " current_photo_version, processing_revision, photo_versions,"
                        + " source_request_id)"
                        + " VALUES (?, ?, 'queued', 1, 1, ?::jsonb, ?)",
                id, gimbalId, photoVersionsJson, t13RequestId);
    }

    /** 补拍字段级 UPDATE：Java 只写照片版本/处理代次/queued 输入状态并清失败列。 */
    public int updateRetake(UUID id, String photoVersionsJson, long newPhotoVersion,
                            long newProcessingRevision) {
        return jdbc.update("UPDATE skin_assessments"
                        + " SET photo_versions = ?::jsonb, current_photo_version = ?,"
                        + " processing_revision = ?, status = 'queued',"
                        + " failure_code = NULL, failure_detail = NULL, updated_at = now()"
                        + " WHERE id = ? AND status = 'needs_retake'",
                photoVersionsJson, newPhotoVersion, newProcessingRevision, id);
    }

    /**
     * M3-A04 游标分页：report_ready 正式报告按 (report_ready_at, id) DESC。
     * fetchSize = limit + 1 用于判断 nextCursor。
     */
    public List<ReportListRow> listReports(UUID memberId, Instant cursorTime, UUID cursorId,
                                           int fetchSize) {
        if (cursorTime == null) {
            return jdbc.query("SELECT id, report_id, report_ready_at, report_summary::text AS report_summary"
                            + " FROM skin_assessments WHERE member_id = ? AND status = 'report_ready'"
                            + " AND report_id IS NOT NULL"
                            + " ORDER BY report_ready_at DESC, id DESC LIMIT ?",
                    (rs, i) -> mapListRow(rs), memberId, fetchSize);
        }
        return jdbc.query("SELECT id, report_id, report_ready_at, report_summary::text AS report_summary"
                        + " FROM skin_assessments WHERE member_id = ? AND status = 'report_ready'"
                        + " AND report_id IS NOT NULL"
                        + " AND (report_ready_at < ? OR (report_ready_at = ? AND id < ?))"
                        + " ORDER BY report_ready_at DESC, id DESC LIMIT ?",
                (rs, i) -> mapListRow(rs), memberId,
                Timestamp.from(cursorTime), Timestamp.from(cursorTime), cursorId, fetchSize);
    }

    private static ReportListRow mapListRow(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new ReportListRow(
                rs.getObject("id", UUID.class),
                rs.getObject("report_id", UUID.class),
                rs.getTimestamp("report_ready_at") == null ? null
                        : rs.getTimestamp("report_ready_at").toInstant(),
                rs.getString("report_summary"));
    }
}

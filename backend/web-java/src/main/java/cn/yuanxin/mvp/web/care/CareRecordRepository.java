package cn.yuanxin.mvp.web.care;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

/**
 * T08 care_records 单表仓储：账本批量判重/插入、收尾聚合与缺口读取；仍提供
 * A07/A09 的记录流水位与确认 ID 分页读取。显式列名，无 JOIN/无关联子查询。
 *
 * <p>判重使用两条批量单表 SELECT（client_record_id 集合 / (source_epoch,
 * source_seq) 集合），绝不逐条 SELECT。</p>
 */
@Repository
public class CareRecordRepository {

    private final JdbcTemplate jdbc;

    public CareRecordRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 已有记录的必要去重字段（payload_hash 为规范化业务内容摘要）。 */
    public record ExistingRecord(UUID id, String clientRecordId, String sourceEpoch,
                                 long sourceSeq, long countDelta, String payloadHash) {
    }

    private static final RowMapper<ExistingRecord> EXISTING_MAPPER = (rs, i) -> new ExistingRecord(
            rs.getObject("id", UUID.class),
            rs.getString("client_record_id"),
            rs.getString("source_epoch"),
            rs.getLong("source_seq"),
            rs.getLong("count_delta"),
            rs.getString("payload_hash"));

    public record NewRecord(UUID id, UUID executionId, String clientRecordId, UUID planId,
                            UUID memberId, UUID microcrystalId, long countDelta, String sourceEpoch,
                            long sourceSeq, Instant occurredAt, Instant receivedAt,
                            String payloadHash, String payloadJson) {
    }

    /** 收尾单表聚合：记录数、最大序号、增量总和。 */
    public record Aggregate(long recordCount, long maxSeq, long totalCount) {
    }

    /** 指定执行流 epoch 下已接受记录的最大 source_seq；无记录或 epoch 为空 → 0。 */
    public long maxSourceSeq(UUID executionId, String sourceEpoch) {
        if (sourceEpoch == null) {
            return 0L;
        }
        Long value = jdbc.queryForObject(
                "SELECT COALESCE(MAX(source_seq), 0) FROM care_records"
                        + " WHERE execution_id = ? AND source_epoch = ?",
                Long.class, executionId, sourceEpoch);
        return value == null ? 0L : value;
    }

    /** client_record_id 按 source_seq 升序分页（source_seq &gt; afterSeq）。 */
    public List<String> clientRecordIdsAfter(UUID executionId, String sourceEpoch,
                                             long afterSeq, int limit) {
        if (sourceEpoch == null) {
            return List.of();
        }
        return jdbc.query("SELECT client_record_id FROM care_records"
                        + " WHERE execution_id = ? AND source_epoch = ? AND source_seq > ?"
                        + " ORDER BY source_seq LIMIT ?",
                (rs, i) -> rs.getString("client_record_id"), executionId, sourceEpoch, afterSeq, limit);
    }

    /** 批量读取已存在记录（client_record_id 集合，单表 IN）。 */
    public List<ExistingRecord> findByClientRecordIds(UUID executionId, Collection<String> recordIds) {
        if (recordIds == null || recordIds.isEmpty()) {
            return List.of();
        }
        List<Object> args = new ArrayList<>();
        args.add(executionId);
        StringBuilder sql = new StringBuilder("SELECT id, client_record_id, source_epoch, source_seq,"
                + " count_delta, payload_hash FROM care_records WHERE execution_id = ?"
                + " AND client_record_id IN (");
        appendPlaceholders(sql, args, recordIds);
        sql.append(')');
        return jdbc.query(sql.toString(), EXISTING_MAPPER, args.toArray());
    }

    /** 批量读取已存在记录（(source_epoch, source_seq) 集合，单表 OR 等值）。 */
    public List<ExistingRecord> findBySeqKeys(UUID executionId, Collection<String[]> seqKeys) {
        if (seqKeys == null || seqKeys.isEmpty()) {
            return List.of();
        }
        List<Object> args = new ArrayList<>();
        args.add(executionId);
        StringBuilder sql = new StringBuilder("SELECT id, client_record_id, source_epoch, source_seq,"
                + " count_delta, payload_hash FROM care_records WHERE execution_id = ? AND (");
        boolean first = true;
        for (String[] key : seqKeys) {
            if (!first) {
                sql.append(" OR ");
            }
            sql.append("(source_epoch = ? AND source_seq = ?)");
            args.add(key[0]);
            args.add(Long.parseLong(key[1]));
            first = false;
        }
        sql.append(')');
        return jdbc.query(sql.toString(), EXISTING_MAPPER, args.toArray());
    }

    public void insert(NewRecord r) {
        jdbc.update("INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id,"
                        + " microcrystal_id, count_delta, source_epoch, source_seq, occurred_at,"
                        + " received_at, payload_hash, payload)"
                        + " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb))",
                r.id(), r.executionId(), r.clientRecordId(), r.planId(), r.memberId(),
                r.microcrystalId(), r.countDelta(), r.sourceEpoch(), r.sourceSeq(),
                r.occurredAt() == null ? null : Timestamp.from(r.occurredAt()),
                Timestamp.from(r.receivedAt()), r.payloadHash(), r.payloadJson());
    }

    /** 收尾核对：COUNT(*)、COALESCE(MAX(source_seq),0)、COALESCE(SUM(count_delta),0)。 */
    public Aggregate aggregate(UUID executionId, String sourceEpoch) {
        if (sourceEpoch == null) {
            return new Aggregate(0L, 0L, 0L);
        }
        return jdbc.queryForObject(
                "SELECT COUNT(*) AS record_count, COALESCE(MAX(source_seq), 0) AS max_seq,"
                        + " COALESCE(SUM(count_delta), 0) AS total_count FROM care_records"
                        + " WHERE execution_id = ? AND source_epoch = ?",
                (rs, i) -> new Aggregate(rs.getLong("record_count"), rs.getLong("max_seq"),
                        rs.getLong("total_count")),
                executionId, sourceEpoch);
    }

    /** epoch 内 source_seq &le; maxSeq 的已存在序号升序（存在多少读多少，绝不物化 1..W）。 */
    public List<Long> sourceSeqsUpTo(UUID executionId, String sourceEpoch, long maxSeq, int limit) {
        if (sourceEpoch == null || maxSeq <= 0) {
            return List.of();
        }
        return jdbc.query("SELECT source_seq FROM care_records"
                        + " WHERE execution_id = ? AND source_epoch = ? AND source_seq <= ?"
                        + " ORDER BY source_seq LIMIT ?",
                (rs, i) -> rs.getLong("source_seq"), executionId, sourceEpoch, maxSeq, limit);
    }

    private static void appendPlaceholders(StringBuilder sql, List<Object> args,
                                           Collection<String> values) {
        boolean first = true;
        for (String value : values) {
            if (!first) {
                sql.append(',');
            }
            sql.append('?');
            args.add(value);
            first = false;
        }
    }
}

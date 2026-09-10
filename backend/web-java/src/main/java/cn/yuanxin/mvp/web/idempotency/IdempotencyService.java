package cn.yuanxin.mvp.web.idempotency;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/**
 * T13 幂等 + 代次控制公共设施（DD 3.3；digest §5；A/decisions #2）。
 *
 * <p>用法（B/C/D 业务写接线的目标模式）：</p>
 * <ol>
 *   <li>{@link #begin} 在<b>独立短事务</b>中插入 processing（唯一键
 *       principal_type+principal_id+operation+idempotency_key）；冲突分支返回
 *       重放/冲突/接管结果；</li>
 *   <li>业务资源写入 + {@link #completeSuccess}/{@link #completeRejected}
 *       在<b>调用方的 TransactionTemplate 事务</b>内提交；</li>
 *   <li>完成语句带代次守卫 WHERE id AND attempt_revision = 我的代次；
 *       0 行 = 已被接管 → {@link StaleAttemptException} 回滚整个业务事务。</li>
 * </ol>
 *
 * <p>succeeded 重放只定位原资源（resourceType/resourceId/resultSummary），
 * 由调用方按当前权限/生命周期投影，不重做写入；rejected 重放返回原拒绝；
 * 同键不同内容 409 IDEMPOTENCY_CONTENT_CONFLICT；processing 且租约存活
 * 409 REQUEST_IN_PROGRESS + Retry-After；租约过期 → 条件更新 attempt_revision
 * 接管。不按短 TTL 删除记录。</p>
 */
@Service
public class IdempotencyService {

    private static final Logger log = LoggerFactory.getLogger(IdempotencyService.class);

    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final ObjectMapper objectMapper;
    private final AppProperties props;

    public IdempotencyService(JdbcTemplate jdbc, TransactionTemplate tx,
                              ObjectMapper objectMapper, AppProperties props) {
        this.jdbc = jdbc;
        this.tx = tx;
        this.objectMapper = objectMapper;
        this.props = props;
    }

    public BeginOutcome begin(String principalType, String principalId, String operation,
                              String idempotencyKey, String payloadHash) {
        UUID id = UUID.randomUUID();
        Instant leaseUntil = Instant.now().plus(Duration.ofSeconds(props.idempotency().leaseSecondsOrDefault()));
        Integer inserted;
        try {
            inserted = tx.execute(s -> jdbc.update(
                    "INSERT INTO idempotency_requests (id, principal_type, principal_id, operation,"
                            + " idempotency_key, payload_hash, status, lease_until, attempt_revision)"
                            + " VALUES (?, ?, ?, ?, ?, ?, 'processing', ?, 1)",
                    id, principalType, principalId, operation, idempotencyKey, payloadHash,
                    Timestamp.from(leaseUntil)));
        } catch (DuplicateKeyException conflict) {
            return resolveExisting(principalType, principalId, operation, idempotencyKey, payloadHash);
        }
        if (inserted == null || inserted != 1) {
            throw new ApiException(ErrorCode.INTERNAL, "idempotency insert failed");
        }
        return new BeginOutcome.NewAttempt(new IdempotencyHandle(id, 1));
    }

    private BeginOutcome resolveExisting(String principalType, String principalId, String operation,
                                         String idempotencyKey, String payloadHash) {
        return tx.execute(s -> {
            var rows = jdbc.query(
                    "SELECT id, status, payload_hash, lease_until, attempt_revision,"
                            + " resource_type, resource_id, result_summary"
                            + " FROM idempotency_requests"
                            + " WHERE principal_type = ? AND principal_id = ? AND operation = ?"
                            + " AND idempotency_key = ?",
                    (rs, i) -> new ExistingRow(
                            rs.getObject("id", UUID.class), rs.getString("status"),
                            rs.getString("payload_hash"),
                            rs.getTimestamp("lease_until") == null ? null : rs.getTimestamp("lease_until").toInstant(),
                            rs.getLong("attempt_revision"), rs.getString("resource_type"),
                            rs.getObject("resource_id", UUID.class),
                            rs.getString("result_summary")),
                    principalType, principalId, operation, idempotencyKey);
            if (rows.isEmpty()) {
                // 竞争：冲突行所属事务回滚了 —— 视为处理中，客户端同键重试
                throw ApiException.requestInProgress(1);
            }
            ExistingRow row = rows.get(0);
            if (!row.payloadHash().equals(payloadHash)) {
                throw new ApiException(ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                        "Idempotency-Key reused with different request content; use a new key for a new logical request");
            }
            switch (row.status()) {
                case "succeeded" -> {
                    return new BeginOutcome.ReplaySucceeded(row.resourceType(), row.resourceId(),
                            readJson(row.resultSummary()));
                }
                case "rejected" -> {
                    JsonNode summary = readJson(row.resultSummary());
                    return new BeginOutcome.ReplayRejected(
                            summary.path("code").asText(ErrorCode.INTERNAL.name()),
                            summary.path("message").asText("original request was rejected"),
                            summary.path("retryable").asBoolean(false),
                            summary.get("details"));
                }
                default -> {
                    Instant now = Instant.now();
                    if (row.leaseUntil() != null && row.leaseUntil().isAfter(now)) {
                        long wait = Math.max(1, Duration.between(now, row.leaseUntil()).toSeconds() + 1);
                        throw ApiException.requestInProgress(wait);
                    }
                    long next = row.attemptRevision() + 1;
                    int updated = jdbc.update(
                            "UPDATE idempotency_requests"
                                    + " SET attempt_revision = ?, lease_until = ?, updated_at = now()"
                                    + " WHERE id = ? AND attempt_revision = ? AND status = 'processing'",
                            next, Timestamp.from(now.plus(Duration.ofSeconds(props.idempotency().leaseSecondsOrDefault()))),
                            row.id(), row.attemptRevision());
                    if (updated == 0) {
                        log.info("idempotency takeover raced: request={}", row.id());
                        throw ApiException.requestInProgress(1);
                    }
                    return new BeginOutcome.NewAttempt(new IdempotencyHandle(row.id(), next));
                }
            }
        });
    }

    /** 业务事务内调用：写 succeeded（同事务提交即幂等结果确立）。 */
    public void completeSuccess(IdempotencyHandle handle, String resourceType, UUID resourceId,
                                Map<String, Object> resultSummary) {
        JsonNode summary = Jcs.toNode(resultSummary);
        ensureSchemaVersion(summary);
        int updated = jdbc.update(
                "UPDATE idempotency_requests"
                        + " SET status = 'succeeded', resource_type = ?, resource_id = ?,"
                        + " result_summary = ?::jsonb, lease_until = NULL, updated_at = now()"
                        + " WHERE id = ? AND attempt_revision = ? AND status = 'processing'",
                resourceType, resourceId, writeJson(summary), handle.requestId(), handle.attemptRevision());
        if (updated == 0) {
            throw new StaleAttemptException(
                    "idempotency request " + handle.requestId() + " no longer owned by attempt "
                            + handle.attemptRevision() + "; business transaction must roll back");
        }
    }

    /** 业务事务内调用：确定性业务拒绝写 rejected（重试返回原拒绝）。 */
    public void completeRejected(IdempotencyHandle handle, ErrorCode code, int httpStatus,
                                 String message, boolean retryable, Map<String, Object> details) {
        var summary = Jcs.objectNode();
        summary.put("code", code.name());
        summary.put("httpStatus", httpStatus);
        summary.put("message", message);
        summary.put("retryable", retryable);
        summary.set("details", details == null ? null : Jcs.toNode(details));
        ensureSchemaVersion(summary);
        int updated = jdbc.update(
                "UPDATE idempotency_requests"
                        + " SET status = 'rejected', result_summary = ?::jsonb,"
                        + " lease_until = NULL, updated_at = now()"
                        + " WHERE id = ? AND attempt_revision = ? AND status = 'processing'",
                writeJson(summary), handle.requestId(), handle.attemptRevision());
        if (updated == 0) {
            throw new StaleAttemptException(
                    "idempotency request " + handle.requestId() + " no longer owned by attempt "
                            + handle.attemptRevision() + "; business transaction must roll back");
        }
    }

    /**
     * 由拒绝重放结果重建原始拒绝（控制器据此向客户端返回同一错误）。
     */
    public static ApiException replayedRejection(BeginOutcome.ReplayRejected replay) {
        ErrorCode code;
        try {
            code = ErrorCode.valueOf(replay.code());
        } catch (IllegalArgumentException e) {
            code = ErrorCode.INTERNAL;
        }
        return new ApiException(code, code.defaultStatus().value(), replay.retryable(),
                replay.message(), replay.details() == null || replay.details().isNull()
                        ? null : objectMapperToMap(replay.details()), Map.of());
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> objectMapperToMap(JsonNode node) {
        try {
            return new ObjectMapper().readValue(node.traverse(), Map.class);
        } catch (Exception e) {
            return Map.of();
        }
    }

    private JsonNode readJson(String raw) {
        if (raw == null || raw.isBlank()) {
            return Jcs.objectNode();
        }
        try {
            return objectMapper.readTree(raw);
        } catch (JsonProcessingException e) {
            log.warn("unparseable idempotency result_summary ignored");
            return Jcs.objectNode();
        }
    }

    /**
     * result_summary 必须携带 schema_version（V1 ck_idem_result_summary_schema；
     * DATA §4"所有 JSONB 有 schema_version"）。调用方未显式给出时服务端注入 1。
     */
    private static void ensureSchemaVersion(JsonNode summary) {
        if (summary instanceof com.fasterxml.jackson.databind.node.ObjectNode obj
                && !obj.has("schema_version")) {
            obj.put("schema_version", 1);
        }
    }

    private String writeJson(JsonNode node) {
        try {
            return objectMapper.writeValueAsString(node);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("result summary serialization failed", e);
        }
    }

    private record ExistingRow(UUID id, String status, String payloadHash, Instant leaseUntil,
                               long attemptRevision, String resourceType, UUID resourceId,
                               String resultSummary) {
    }
}

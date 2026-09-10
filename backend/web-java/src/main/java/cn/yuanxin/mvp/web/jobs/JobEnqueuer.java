package cn.yuanxin.mvp.web.jobs;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.UncategorizedSQLException;

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Savepoint;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.UUID;

/**
 * T12 async_jobs 入队器（A/decisions #14；digest §4）。
 *
 * <p>必须在<b>调用方的业务 TransactionTemplate 事务内</b>调用——受理业务写 +
 * 插任务一次提交即完成 Java→Python 交接（无回调 HTTP、无跨语言分布式事务）。</p>
 *
 * <ul>
 *   <li>payload：snake_case JSON；必须含 schema_version（JSON 整数）；
 *       bigint 一律十进制字符串（调用方保证）；</li>
 *   <li>dedup_key 唯一冲突 = 同一逻辑任务已入队 → 视作重放返回既有 jobId，
 *       不报错（幂等入队）；</li>
 *   <li>owner_type 枚举 {assessment, plan, notification, media,
 *       identity_namespace, system}（contracts decisions-notes §3）；
 *       identity_namespace/system 的 owner_id 用 {@link #systemOwnerFor}/
 *       {@link #identityNamespaceOwnerFor}（UUIDv5 FIXED_NS，两侧字节一致输入）。</li>
 * </ul>
 */
@Component
public class JobEnqueuer {

    private static final Logger log = LoggerFactory.getLogger(JobEnqueuer.class);

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public JobEnqueuer(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public record JobEnqueueResult(UUID jobId, String dedupKey, String status, boolean replayed) {
    }

    /** 初值：status=queued、available_at=now、attempt_count=0、max_attempts=5、lease_revision=0。 */
    public JobEnqueueResult enqueue(String jobType, String ownerType, UUID ownerId, long inputRevision,
                                    Map<String, Object> payload, String dedupKey) {
        String payloadJson;
        try {
            payloadJson = objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("job payload is not serializable JSON", e);
        }
        if (!payload.containsKey("schema_version")) {
            throw new IllegalArgumentException("job payload must carry schema_version (DD 9.1)");
        }
        UUID id = UUID.randomUUID();
        try {
            // PG 在事务内遇到唯一冲突会 abort 整个事务（25P02）。用 JDBC savepoint
            // 局部回滚本次 INSERT，调用方的业务事务保持存活（decisions #14：
            // dedup 冲突=同一逻辑任务已入队，视作重放而非错误）。
            return jdbc.execute((ConnectionCallback<JobEnqueueResult>) con -> {
                Savepoint point = con.setSavepoint("mvp_job_insert");
                try {
                    try (var ps = con.prepareStatement(
                            "INSERT INTO async_jobs (id, job_type, dedup_key, owner_type, owner_id,"
                                    + " input_revision, payload, status, available_at, attempt_count,"
                                    + " max_attempts, lease_revision)"
                                    + " VALUES (?, ?, ?, ?, ?, ?, ?::jsonb, 'queued', now(), 0, 5, 0)")) {
                        ps.setObject(1, id);
                        ps.setObject(2, jobType);
                        ps.setObject(3, dedupKey);
                        ps.setObject(4, ownerType);
                        ps.setObject(5, ownerId);
                        ps.setObject(6, inputRevision);
                        ps.setObject(7, payloadJson);
                        ps.executeUpdate();
                    }
                    return new JobEnqueueResult(id, dedupKey, "queued", false);
                } catch (SQLException dup) {
                    con.rollback(point);
                    var rows = jdbc.query("SELECT id, status FROM async_jobs WHERE dedup_key = ?",
                            (rs, i) -> new JobEnqueueResult(rs.getObject("id", UUID.class), dedupKey,
                                    rs.getString("status"), true),
                            dedupKey);
                    if (rows.isEmpty()) {
                        throw new IllegalStateException("dedup conflict but row vanished: " + dedupKey, dup);
                    }
                    log.info("job enqueue dedup replay: type={} dedupKey={} jobId={}", jobType, dedupKey,
                            rows.get(0).jobId());
                    return rows.get(0);
                }
            });
        } catch (DuplicateKeyException conflict) {
            var rows = jdbc.query("SELECT id, status FROM async_jobs WHERE dedup_key = ?",
                    (rs, i) -> new JobEnqueueResult(rs.getObject("id", UUID.class), dedupKey,
                            rs.getString("status"), true),
                    dedupKey);
            if (rows.isEmpty()) {
                throw conflict;
            }
            return rows.get(0);
        }
    }

    /** owner_type=system：owner_id = uuid5(FIXED_NS, dedup_key)（decisions #3）。 */
    public static UUID systemOwnerFor(String dedupKey) {
        return Uuid5.uuid5(Uuid5.FIXED_NS, dedupKey);
    }

    /** owner_type=identity_namespace：owner_id = uuid5(FIXED_NS, "<ns>:<faceSubjectRef>")。 */
    public static UUID identityNamespaceOwnerFor(String identityNamespace, String faceSubjectRef) {
        return Uuid5.uuid5(Uuid5.FIXED_NS, identityNamespace + ":" + faceSubjectRef);
    }
}

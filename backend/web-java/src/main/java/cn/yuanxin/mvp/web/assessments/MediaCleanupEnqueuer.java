package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.jobs.JobEnqueuer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 未接纳媒体孤儿补偿入队（裁定 5，Java 侧触发；DD 10.3）。
 *
 * <p>业务拒绝提交后或业务事务异常回滚后，按 T13 request_id 单表查未接纳
 * （assessment_id IS NULL）且可清理状态（pending/available/failed）的 T11 行，
 * 为每个 mediaId 在<b>各自独立的短事务</b>内入队 media.cleanup：
 * {@code owner_type='media'}、{@code owner_id=mediaId}、{@code input_revision=1}、
 * {@code dedup_key="media:{id}:cleanup:1"}、payload 严格匹配
 * contracts/schemas/payload-media-cleanup.json。</p>
 *
 * <p><b>尽力而为</b>：任何查询/入队异常只记 warn，绝不上抛，绝不改变或掩盖
 * 主 HTTP 响应。</p>
 */
@Component
public class MediaCleanupEnqueuer {

    private static final Logger log = LoggerFactory.getLogger(MediaCleanupEnqueuer.class);

    public static final String JOB_TYPE = "media.cleanup";
    private static final long CLEANUP_REVISION = 1L;

    private final JdbcTemplate jdbc;
    private final JobEnqueuer jobEnqueuer;
    private final TransactionTemplate txTemplate;

    public MediaCleanupEnqueuer(JdbcTemplate jdbc, JobEnqueuer jobEnqueuer,
                                TransactionTemplate txTemplate) {
        this.jdbc = jdbc;
        this.jobEnqueuer = jobEnqueuer;
        this.txTemplate = txTemplate;
    }

    public void enqueueOrphansFor(UUID t13RequestId) {
        if (t13RequestId == null) {
            return;
        }
        List<UUID> mediaIds;
        try {
            mediaIds = jdbc.queryForList("SELECT id FROM media_objects"
                            + " WHERE request_id = ? AND assessment_id IS NULL"
                            + " AND state IN ('pending','available','failed')",
                    UUID.class, t13RequestId);
        } catch (RuntimeException e) {
            log.warn("media.cleanup orphan lookup failed for request {}: {}", t13RequestId,
                    e.toString());
            return;
        }
        for (UUID mediaId : mediaIds) {
            try {
                txTemplate.executeWithoutResult(status -> jobEnqueuer.enqueue(JOB_TYPE, "media",
                        mediaId, CLEANUP_REVISION, cleanupPayload(mediaId),
                        dedupKey(mediaId)));
            } catch (RuntimeException e) {
                log.warn("media.cleanup enqueue failed for mediaId {}: {}", mediaId, e.toString());
            }
        }
    }

    private static Map<String, Object> cleanupPayload(UUID mediaId) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schema_version", 1);
        payload.put("media_object_id", mediaId.toString());
        payload.put("cleanup_revision", String.valueOf(CLEANUP_REVISION));
        return payload;
    }

    private static String dedupKey(UUID mediaId) {
        return "media:" + mediaId + ":cleanup:" + CLEANUP_REVISION;
    }
}

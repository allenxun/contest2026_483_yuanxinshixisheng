package cn.yuanxin.mvp.web.assessments;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.UUID;

/**
 * T11 media_objects 归属补齐（Java 写边界：assessment_id/photo_version）。
 * 只接纳本请求创建、state=available 的行；0 行 = 越权/状态不符，调用方回滚。
 */
@Repository
public class AssessmentMediaRepository {

    private final JdbcTemplate jdbc;

    public AssessmentMediaRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int claim(UUID mediaId, UUID assessmentId, long photoVersion, UUID requestId) {
        return jdbc.update("UPDATE media_objects"
                        + " SET assessment_id = ?, photo_version = ?, updated_at = now()"
                        + " WHERE id = ? AND state = 'available' AND request_id = ?",
                assessmentId, photoVersion, mediaId, requestId);
    }
}

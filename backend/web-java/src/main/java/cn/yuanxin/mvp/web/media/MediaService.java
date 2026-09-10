package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;

import java.io.InputStream;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/**
 * 媒体元数据基础服务（DD 10.1 / digest §7）：
 * pending → (StoragePort 写入 + 校验) → available；失败路径 state=failed + last_error。
 *
 * <p>对象 key = {@code <env>/<purpose>/<random-uuid>}，服务端生成、不含
 * 姓名/手机号等 PII（DD 10.1）。上传流程扩展点：B/C/D 在受理事务里引用
 * 本服务产出的 available mediaId 补归属（T11 归属列是 Java 写边界）。</p>
 */
@Service
public class MediaService {

    private static final Logger log = LoggerFactory.getLogger(MediaService.class);

    private final JdbcTemplate jdbc;
    private final StoragePort storage;
    private final AppProperties props;
    private final ObjectMapper objectMapper;

    public MediaService(JdbcTemplate jdbc, StoragePort storage, AppProperties props,
                        ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.storage = storage;
        this.props = props;
        this.objectMapper = objectMapper;
    }

    private static final RowMapper<MediaObject> MAPPER = (rs, i) -> {
        String purpose = rs.getString("purpose");
        Long byteSize = rs.getLong("byte_size");
        return new MediaObject(
                rs.getObject("id", UUID.class),
                rs.getString("bucket"),
                rs.getString("object_key"),
                purpose == null ? null : MediaPurpose.fromDbValue(purpose),
                rs.getString("state"),
                rs.getString("uploader_type"),
                rs.getString("uploader_ref"),
                rs.getObject("request_id", UUID.class),
                rs.getString("content_type"),
                rs.wasNull() ? null : byteSize,
                rs.getString("content_hash"));
    };

    /** 建立 pending 行（key 服务端生成；bucket 来自配置，无 PII）。 */
    public MediaObject createPending(MediaPurpose purpose, String uploaderType,
                                     String uploaderRef, UUID requestId) {
        UUID id = UUID.randomUUID();
        String objectKey = props.env() + "/" + purpose.dbValue() + "/" + id;
        try {
            jdbc.update("INSERT INTO media_objects (id, bucket, object_key, purpose, uploader_type,"
                            + " uploader_ref, request_id, state)"
                            + " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
                    id, props.storage().bucket(), objectKey, purpose.dbValue(),
                    uploaderType, uploaderRef, requestId);
        } catch (DuplicateKeyException e) {
            // (bucket, object_key) 理论不冲突（随机 uuid）；冲突视为内部错误
            throw new IllegalStateException("media object key collision", e);
        }
        return new MediaObject(id, props.storage().bucket(), objectKey, purpose, "pending",
                uploaderType, uploaderRef, requestId, null, null, null);
    }

    /** StoragePort 写入并校验（content-type 白名单 image/*、大小上限）后标 available。 */
    public MediaObject markAvailable(UUID mediaId, String contentType, long byteSize,
                                     String contentSha256Hex) {
        if (contentType == null || !contentType.startsWith("image/")) {
            fail(mediaId, ErrorCode.UNSUPPORTED_IMAGE, "content type not in image/* whitelist");
            throw new ApiException(ErrorCode.UNSUPPORTED_IMAGE,
                    "only image content is accepted");
        }
        if (byteSize < 0 || byteSize > props.limits().maxImageBytes()) {
            fail(mediaId, ErrorCode.UPLOAD_TOO_LARGE, "byte size exceeds configured limit");
            throw new ApiException(ErrorCode.UPLOAD_TOO_LARGE,
                    "image exceeds max byte size " + props.limits().maxImageBytes());
        }
        int updated = jdbc.update("UPDATE media_objects"
                        + " SET state = 'available', content_type = ?, byte_size = ?, content_hash = ?,"
                        + " storage_metadata = ?::jsonb, last_error = NULL, updated_at = now()"
                        + " WHERE id = ? AND state = 'pending'",
                contentType, byteSize, contentSha256Hex,
                "{\"upgraded_by\":\"foundation-media\"}", mediaId);
        if (updated == 0) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, "media object not found");
        }
        return load(mediaId);
    }

    /** 失败路径：pending → failed + 可诊断 last_error（不含供应商密钥级细节）。 */
    public void fail(UUID mediaId, ErrorCode code, String message) {
        String err;
        try {
            err = objectMapper.writeValueAsString(Map.of("code", code.name(), "message",
                    message == null ? "" : message));
        } catch (Exception e) {
            err = "{\"code\":\"" + code.name() + "\"}";
        }
        jdbc.update("UPDATE media_objects SET state = 'failed', last_error = ?::jsonb,"
                + " updated_at = now() WHERE id = ? AND state IN ('pending','available')", err, mediaId);
    }

    /** 行读取（不存在 → null；调用方转 404 RESOURCE_NOT_VISIBLE）。 */
    public MediaObject load(UUID mediaId) {
        var rows = jdbc.query("SELECT id, bucket, object_key, purpose, state, uploader_type,"
                + " uploader_ref, request_id, content_type, byte_size, content_hash"
                + " FROM media_objects WHERE id = ?", MAPPER, mediaId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /** 受控内容流：仅 available 可见；存储缺对象按不可见处理（不泄露 bucket/key）。 */
    public InputStream openContent(MediaObject media) {
        if (media == null || !"available".equals(media.state())) {
            return null;
        }
        InputStream in = storage.getStream(media.objectKey());
        if (in == null) {
            log.warn("media content missing in storage for mediaId={}; treating as not visible",
                    media.id());
        }
        return in;
    }
}

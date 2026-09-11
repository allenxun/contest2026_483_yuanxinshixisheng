package cn.yuanxin.mvp.web.mediapolicy;

import cn.yuanxin.mvp.web.media.MediaPurpose;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/**
 * 裁定验证：<b>任何 env 下都不得委派</b>，不存在 dev owner 便利旁路。
 *
 * <p>显式开启 {@code app.media.access-mode=owner-dev}（旧实现下会让上传者便利
 * 放行非 face 用途），但 B 的 {@code @Primary} 策略绝不委派：上传者本人读取
 * 自己的 {@code assessment_result} 图片仍被拒绝；face 用途同样拒绝。若此测试
 * 出现 200，说明委派旁路被重新引入。</p>
 *
 * <p>与 A 的 {@code OwnerDevMediaAccessIT} 使用同一测试属性（共享 Spring 上下文）。</p>
 */
@TestPropertySource(properties = "app.media.access-mode=owner-dev")
class MediaPolicyNoDelegationIT extends AbstractWebIT {

    private static final byte[] PNG = "PNG-NO-DELEGATION-BYTES".getBytes(StandardCharsets.UTF_8);

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    StoragePort storagePort;

    private UUID seedMedia(UUID id, MediaPurpose purpose, String uploaderRef) {
        String objectKey = "test/" + purpose.dbValue() + "/" + id;
        storagePort.put(objectKey, new ByteArrayInputStream(PNG), PNG.length, "image/png");
        jdbc.update("INSERT INTO media_objects (id, bucket, object_key, purpose, member_id,"
                        + " uploader_type, uploader_ref, state, content_type, byte_size, content_hash,"
                        + " storage_metadata)"
                        + " VALUES (?, 'mvp-a-test', ?, ?, NULL, 'app', ?, 'available', 'image/png', ?, ?,"
                        + " '{\"schema_version\":1}'::jsonb)",
                id, objectKey, purpose.dbValue(), uploaderRef, (long) PNG.length, sha256Hex(PNG));
        return id;
    }

    @Test
    @DisplayName("owner-dev 配置下上传者本人仍被拒绝：assessment_result / assessment_source / face 全部 404（无委派旁路）")
    void ownerDevConfigurationNeverDelegates() throws Exception {
        String installationId = "inst-del-" + UUID.randomUUID().toString().substring(0, 8);
        LoginResult owner = loginAppWithInstallation(newPhone(), installationId);
        UUID accountId = UUID.fromString(owner.accountId());
        String uploaderRef = accountId + ":" + installationId;

        for (MediaPurpose purpose : new MediaPurpose[]{MediaPurpose.ASSESSMENT_RESULT,
                MediaPurpose.ASSESSMENT_SOURCE, MediaPurpose.GRANT_FACE,
                MediaPurpose.EXECUTION_FACE, MediaPurpose.REVALIDATION_FACE}) {
            UUID mediaId = seedMedia(UUID.randomUUID(), purpose, uploaderRef);
            MvcResult r = mockMvc.perform(get("/api/v1/media/" + mediaId + "/content")
                            .header("Authorization", "Bearer " + owner.accessToken()))
                    .andReturn();
            assertEquals(404, r.getResponse().getStatus(),
                    "owner-dev 下也必须拒绝 " + purpose.dbValue() + ": "
                            + r.getResponse().getContentAsString());
        }
    }

    private static String sha256Hex(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}

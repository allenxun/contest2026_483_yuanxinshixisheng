package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/** 媒体基础：pending key 形状、markAvailable 完整性、白名单/超限失败、受控读取。 */
class MediaFoundationIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    MediaService mediaService;

    @Autowired
    MediaIntakeService intakeService;

    private static final byte[] PNG = new byte[]{(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A,
            0, 0, 0, 9, 'I', 'H', 'D', 'R'};

    @Test
    @DisplayName("createPending：key=<env>/<purpose>/<uuid>，DB state=pending")
    void pendingKeyFormat() {
        MediaObject m = mediaService.createPending(MediaPurpose.GRANT_FACE, "app_account",
                "acct:inst", null);
        assertTrue(Pattern.matches("test/grant_face/[0-9a-f-]{36}", m.objectKey()), m.objectKey());
        Map<String, Object> row = jdbc.queryForMap(
                "SELECT state, bucket, purpose FROM media_objects WHERE id = ?", m.id());
        assertEquals("pending", row.get("state"));
        assertEquals("mvp-a-test", row.get("bucket"));
        assertEquals("grant_face", row.get("purpose"));
    }

    @Test
    @DisplayName("markAvailable 持久化完整性字段；白名单外 → 415 + failed；超限 → 413 + failed")
    void markAvailableAndFailPaths() {
        MediaObject m = mediaService.createPending(MediaPurpose.ASSESSMENT_SOURCE,
                "gimbal", "g-1", null);
        MediaObject avail = mediaService.markAvailable(m.id(), "image/jpeg", 1234L,
                "a".repeat(64));
        assertEquals("available", avail.state());
        Map<String, Object> row = jdbc.queryForMap(
                "SELECT content_type, byte_size, content_hash FROM media_objects WHERE id = ?",
                m.id());
        assertEquals("image/jpeg", row.get("content_type"));
        assertEquals(1234L, ((Number) row.get("byte_size")).longValue());
        assertEquals("a".repeat(64), row.get("content_hash"));

        MediaObject pdf = mediaService.createPending(MediaPurpose.EXECUTION_FACE, "app_account",
                "a:1", null);
        ApiException e1 = assertThrows(ApiException.class,
                () -> mediaService.markAvailable(pdf.id(), "application/pdf", 10L, "b"));
        assertEquals(ErrorCode.UNSUPPORTED_IMAGE, e1.getCode());
        assertEquals("failed", jdbc.queryForObject(
                "SELECT state FROM media_objects WHERE id = ?", String.class, pdf.id()));

        MediaObject big = mediaService.createPending(MediaPurpose.REVALIDATION_FACE, "app_account",
                "a:1", null);
        ApiException e2 = assertThrows(ApiException.class, () -> mediaService.markAvailable(
                big.id(), "image/png", 20 * 1024 * 1024L, "c"));
        assertEquals(ErrorCode.UPLOAD_TOO_LARGE, e2.getCode());
        assertEquals("failed", jdbc.queryForObject(
                "SELECT state FROM media_objects WHERE id = ?", String.class, big.id()));
    }

    @Test
    @DisplayName("MediaIntakeService：逐 part 摘要→pending→storage→available；实际格式嗅探")
    void intakeFlow() {
        var principal = cn.yuanxin.mvp.web.auth.PrincipalContext.forApp(
                cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal.app(UUID.randomUUID(), "inst", "s", 1L),
                "req-1");
        Map<String, MediaIntakeService.IngestedMedia> out = intakeService.ingest(
                principal, MediaPurpose.ASSESSMENT_SOURCE, null, Map.of("front", PNG));
        MediaIntakeService.IngestedMedia ing = out.get("front");
        assertEquals("available", ing.media().state());
        assertEquals("image/png", ing.contentType());
        assertEquals(MediaIntakeService.sha256Hex(PNG), ing.sha256Hex());
        assertTrue(StorageDoubleProbe.existsUnder("/tmp/mvp-a-test-storage", ing.media().objectKey()));
        // 非图片字节 → UNSUPPORTED_IMAGE，行 failed
        assertThrows(ApiException.class, () -> intakeService.ingest(principal,
                MediaPurpose.ASSESSMENT_SOURCE, null,
                Map.of("front", new byte[]{1, 2, 3, 4, 5, 6, 7, 8})));
    }

    @Test
    @DisplayName("GET content 默认 deny-all：上传者/他人/同账号换安装/未知/pending 一律 404 RESOURCE_NOT_VISIBLE；无 token 401")
    void defaultDenyAllEverything() throws Exception {
        String ownerPhone = newPhone();
        LoginResult owner = loginAppWithInstallation(ownerPhone, "inst-deny-owner");
        var ownerPrincipal = cn.yuanxin.mvp.web.auth.PrincipalContext.forApp(
                cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal.app(
                        UUID.fromString(owner.accountId()), "inst-deny-owner", "s-deny", 1L),
                "req-deny");
        // 非人脸用途的 available 媒体（owner-dev 便利都不启用时同样不可读）
        MediaIntakeService.IngestedMedia ing = intakeService.ingest(
                ownerPrincipal, MediaPurpose.ASSESSMENT_RESULT, null, Map.of("shot", PNG))
                .values().iterator().next();
        assertEquals("available", ing.media().state());

        // 上传者本人 → 仍 404（生产安全默认 deny-all）
        assertNotVisible(owner.accessToken(), ing.media().id(), 404);

        // 其他已认证 principal → 404
        LoginResult other = loginAppWithInstallation(newPhone(), "inst-deny-other");
        assertNotVisible(other.accessToken(), ing.media().id(), 404);

        // 同账号、不同 installation → 404
        LoginResult sameAcctOtherInst = loginAppWithInstallation(ownerPhone, "inst-deny-owner-2");
        assertNotVisible(sameAcctOtherInst.accessToken(), ing.media().id(), 404);

        // pending（未受理完成）→ 404
        MediaObject pending = mediaService.createPending(MediaPurpose.ASSESSMENT_RESULT,
                "app_account", "a:1", null);
        assertNotVisible(owner.accessToken(), pending.id(), 404);

        // 未知 id → 404
        assertNotVisible(owner.accessToken(), UUID.randomUUID(), 404);

        // 无 token → 401（认证先于可见性）
        MvcResult anon = mockMvc.perform(get("/api/v1/media/" + ing.media().id() + "/content"))
                .andReturn();
        assertEquals(401, anon.getResponse().getStatus());
    }

    @Test
    @DisplayName("GET content 默认 deny-all：GRANT_FACE 已 available 但上传者也 404（核验用途保留给业务策略）")
    void facePurposeDeniedEvenForUploaderDefaultMode() throws Exception {
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-face-deny");
        var ownerPrincipal = cn.yuanxin.mvp.web.auth.PrincipalContext.forApp(
                cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal.app(
                        UUID.fromString(owner.accountId()), "inst-face-deny", "s-face", 1L),
                "req-face");
        MediaIntakeService.IngestedMedia face = intakeService.ingest(
                ownerPrincipal, MediaPurpose.GRANT_FACE, null, Map.of("face", PNG))
                .values().iterator().next();
        assertEquals("available", face.media().state());
        assertNotVisible(owner.accessToken(), face.media().id(), 404);
    }

    private void assertNotVisible(String token, UUID mediaId, int expectedStatus) throws Exception {
        MvcResult r = mockMvc.perform(get("/api/v1/media/" + mediaId + "/content")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(expectedStatus, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        if (expectedStatus == 404) {
            JsonNode err = JSON.readTree(r.getResponse().getContentAsString());
            assertEquals("RESOURCE_NOT_VISIBLE", err.path("error").path("code").asText());
        }
    }

    /** 存储替身文件探针（路径安全 normalize）。 */
    static final class StorageDoubleProbe {
        static boolean existsUnder(String root, String key) {
            java.nio.file.Path p = java.nio.file.Path.of(root).resolve(key).normalize();
            return java.nio.file.Files.isRegularFile(p);
        }
    }
}

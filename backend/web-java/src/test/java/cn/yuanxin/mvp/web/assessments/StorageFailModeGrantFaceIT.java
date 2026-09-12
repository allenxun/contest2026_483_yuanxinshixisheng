package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.identity.MemberAccessGrantService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

/**
 * SC-C-05（Java 侧）受控存储失败注入，反向隔离：
 * {@code APP_DOUBLE_STORAGE_FAIL_MODE=fail-put:grant_face} 只失败 M1-A01
 * 人脸上传（grant_face），云台原图（M3-A01，assessment_source）必须仍成功。
 */
@TestPropertySource(properties = {
        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put:grant_face",
        "app.storage.dev-dir=target/storage-it/grant-face-fail"
})
class StorageFailModeGrantFaceIT extends AssessmentTestSupport {

    private static final byte[] PNG_HEADER = {
            (byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};

    private static byte[] faceBytes(String tag) {
        byte[] body = tag.getBytes(StandardCharsets.UTF_8);
        byte[] out = new byte[PNG_HEADER.length + body.length];
        System.arraycopy(PNG_HEADER, 0, out, 0, PNG_HEADER.length);
        System.arraycopy(body, 0, out, PNG_HEADER.length, body.length);
        return out;
    }

    private static MockMultipartFile grantMetadata(String captureId) {
        String json = "{\"capture\":{\"captureId\":\"" + captureId + "\","
                + "\"capturedAt\":\"2026-09-11T10:00:00Z\","
                + "\"clientContinuityId\":\"cont-" + captureId + "\",\"purpose\":\"grant\"},"
                + "\"consentEvidenceRef\":\"consent-" + captureId + "\"}";
        return new MockMultipartFile("metadata", "metadata", "application/json",
                json.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    @DisplayName("SC-C-05：fail-put:grant_face → M1-A01 上传 503，无 available 脏行、无 grant 行")
    void grantFaceUploadFailureIs503AndNoDirtySuccess() throws Exception {
        LoginResult account = loginAppWithInstallation(newPhone(),
                "inst-" + UUID.randomUUID().toString().substring(0, 8));
        UUID accountId = UUID.fromString(account.accountId());
        String key = "k-grant-storefail-" + UUID.randomUUID();

        MvcResult r = mockMvc.perform(multipart("/api/v1/member-access-grants")
                        .file(grantMetadata("cap-fail-" + key))
                        .file(new MockMultipartFile("face", "face.png", "image/png",
                                faceBytes("fail-" + UUID.randomUUID())))
                        .header("Authorization", "Bearer " + account.accessToken())
                        .header("Idempotency-Key", key))
                .andReturn();

        assertEquals(503, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("DEPENDENCY_UNAVAILABLE", error(r).path("code").asText());

        UUID t13 = jdbc.queryForObject("SELECT id FROM idempotency_requests"
                        + " WHERE operation = ? AND idempotency_key = ?", UUID.class,
                MemberAccessGrantService.OP_CREATE, key);
        Integer available = jdbc.queryForObject("SELECT count(*) FROM media_objects"
                        + " WHERE request_id = ? AND state = 'available'", Integer.class, t13);
        assertEquals(0, available, "存储失败后不得留下 available 媒体行");
        Integer failed = jdbc.queryForObject("SELECT count(*) FROM media_objects"
                        + " WHERE request_id = ? AND purpose = 'grant_face' AND state = 'failed'",
                Integer.class, t13);
        assertEquals(1, failed, "pending 人脸行必须被标 failed");
        Integer grants = jdbc.queryForObject("SELECT count(*) FROM member_access_grants"
                + " WHERE account_id = ?", Integer.class, accountId);
        assertEquals(0, grants, "存储失败不得创建 grant");
        assertNotEquals("succeeded", jdbc.queryForObject("SELECT status FROM idempotency_requests"
                + " WHERE id = ?", String.class, t13), "T13 不得记 succeeded");
    }

    @Test
    @DisplayName("SC-C-05 隔离：grant_face 失败时 M3-A01 云台原图仍 202 且对象 available")
    void assessmentSourceUploadUnaffectedByGrantFaceFailure() throws Exception {
        GimbalFixture gimbal = createGimbal();
        String key = "d-a01-iso-" + UUID.randomUUID();
        MvcResult r = postA01(gimbal.token(), key);

        assertEquals(202, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        UUID t13 = t13IdForGimbalKey(gimbal.gimbalId(), key);
        Integer available = jdbc.queryForObject("SELECT count(*) FROM media_objects"
                        + " WHERE request_id = ? AND purpose = 'assessment_source'"
                        + " AND state = 'available'",
                Integer.class, t13);
        assertEquals(3, available, "assessment_source 三个视角均应 available");
        assertTrue(jdbc.queryForObject("SELECT count(*) FROM skin_assessments"
                + " WHERE source_request_id = ?", Integer.class, t13) == 1);
    }
}

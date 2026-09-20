package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.identity.DevTestFaceIdentityResolver;
import cn.yuanxin.mvp.web.identity.FaceIdentityResolver;
import cn.yuanxin.mvp.web.identity.MemberAccessGrantService;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

/**
 * SC-C-05（Java 侧）受控存储失败注入，经真实 HTTP 入口驱动，开关
 * {@code APP_DOUBLE_STORAGE_FAIL_MODE=fail-put:assessment_source}：
 * 只失败云台原图（M3-A01/A02）写入，APP 授权/核验照片（M1-A01，grant_face）
 * 必须不受影响 —— 证明按 purpose 的可选择性与隔离。
 *
 * <p>断言无脏成功：失败请求的 T11 无 available 行、无新增任务/报告；
 * 响应为既有映射 503 {@code DEPENDENCY_UNAVAILABLE}。</p>
 */
@TestPropertySource(properties = {
        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put:assessment_source",
        "app.storage.dev-dir=target/storage-it/assessment-source-fail"
})
class StorageFailModeAssessmentSourceIT extends AssessmentTestSupport {

    private static final byte[] PNG_HEADER = {
            (byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};

    @Autowired
    FaceIdentityResolver faceIdentityResolver;

    private static byte[] faceBytes(String tag) {
        byte[] body = tag.getBytes(StandardCharsets.UTF_8);
        byte[] out = new byte[PNG_HEADER.length + body.length];
        System.arraycopy(PNG_HEADER, 0, out, 0, PNG_HEADER.length);
        System.arraycopy(body, 0, out, PNG_HEADER.length, body.length);
        return out;
    }

    private static String retakeMetadata(long expected, String... views) {
        StringBuilder sb = new StringBuilder("{\"expectedPhotoVersion\":\"").append(expected)
                .append("\",\"replacedViews\":[");
        for (int i = 0; i < views.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append('"').append(views[i]).append('"');
        }
        return sb.append("]}").toString();
    }

    private void assertNoDirtySuccess(UUID requestId, UUID gimbalId) {
        Integer available = jdbc.queryForObject("SELECT count(*) FROM media_objects"
                + " WHERE request_id = ? AND state = 'available'", Integer.class, requestId);
        assertEquals(0, available, "存储写失败后不得留下 available 媒体行（脏成功）");
        Integer failed = jdbc.queryForObject("SELECT count(*) FROM media_objects"
                + " WHERE request_id = ? AND state = 'failed'", Integer.class, requestId);
        assertTrue(failed >= 1, "pending 行必须被标 failed");
        Integer tasks = jdbc.queryForObject("SELECT count(*) FROM skin_assessments"
                + " WHERE source_request_id = ?", Integer.class, requestId);
        assertEquals(0, tasks, "上传失败不得创建测肤任务");
        Integer ready = jdbc.queryForObject("SELECT count(*) FROM skin_assessments"
                + " WHERE gimbal_id = ? AND status = 'report_ready'", Integer.class, gimbalId);
        assertEquals(0, ready, "不得出现 report_ready（绝不伪报成功）");
    }

    @Test
    @DisplayName("SC-C-05：fail-put:assessment_source → M3-A01 上传 503 DEPENDENCY_UNAVAILABLE，无脏成功")
    void a01UploadFailureIs503AndNoDirtySuccess() throws Exception {
        GimbalFixture gimbal = createGimbal();
        String key = "d-a01-storefail-" + UUID.randomUUID();
        MvcResult r = postA01(gimbal.token(), key);

        assertEquals(503, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("DEPENDENCY_UNAVAILABLE", error(r).path("code").asText());
        assertNoDirtySuccess(t13IdForGimbalKey(gimbal.gimbalId(), key), gimbal.gimbalId());
    }

    @Test
    @DisplayName("SC-C-05：fail-put:assessment_source → M3-A02 补拍上传 503 DEPENDENCY_UNAVAILABLE，无脏成功")
    void a02UploadFailureIs503AndNoDirtySuccess() throws Exception {
        GimbalFixture gimbal = createGimbal();
        String key = "d-a02-storefail-" + UUID.randomUUID();
        MvcResult r = putA02(gimbal.token(), key, UUID.randomUUID(), 2,
                retakeMetadata(1, "left"), Map.of("left", png(11)));

        assertEquals(503, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("DEPENDENCY_UNAVAILABLE", error(r).path("code").asText());
        assertNoDirtySuccess(t13IdForGimbalKey(gimbal.gimbalId(), key), gimbal.gimbalId());
    }

    @Test
    @DisplayName("SC-C-05 隔离：assessment_source 失败时 M1-A01 人脸上传（grant_face）仍 201 且对象 available")
    void grantFaceUploadUnaffectedByAssessmentSourceFailure() throws Exception {
        LoginResult account = loginAppWithInstallation(newPhone(),
                "inst-" + UUID.randomUUID().toString().substring(0, 8));
        byte[] face = faceBytes("iso-" + UUID.randomUUID());
        UUID memberId = UUID.randomUUID();
        jdbc.update("INSERT INTO members (id, identity_namespace, face_subject_ref)"
                        + " VALUES (?, ?, ?)",
                memberId, faceIdentityResolver.identityNamespace(),
                DevTestFaceIdentityResolver.subjectRefFor(face));

        String key = "k-grant-iso-" + UUID.randomUUID();
        MvcResult r = mockMvc.perform(multipart("/api/v1/member-access-grants")
                        .file(grantMetadata("cap-iso-" + key))
                        .file(new MockMultipartFile("face", "face.png", "image/png", face))
                        .header("Authorization", "Bearer " + account.accessToken())
                        .header("Idempotency-Key", key))
                .andReturn();

        assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        UUID t13 = jdbc.queryForObject("SELECT id FROM idempotency_requests"
                        + " WHERE operation = ? AND idempotency_key = ?", UUID.class,
                MemberAccessGrantService.OP_CREATE, key);
        Integer available = jdbc.queryForObject("SELECT count(*) FROM media_objects"
                        + " WHERE request_id = ? AND purpose = 'grant_face' AND state = 'available'",
                Integer.class, t13);
        assertEquals(1, available, "grant_face 写入不得受 assessment_source 注入影响");
        Integer failed = jdbc.queryForObject("SELECT count(*) FROM media_objects"
                + " WHERE request_id = ? AND state = 'failed'", Integer.class, t13);
        assertEquals(0, failed);
    }

    private static MockMultipartFile grantMetadata(String captureId) {
        String json = "{\"capture\":{\"captureId\":\"" + captureId + "\","
                + "\"capturedAt\":\"2026-09-11T10:00:00Z\","
                + "\"clientContinuityId\":\"cont-" + captureId + "\",\"purpose\":\"grant\"},"
                + "\"consentEvidenceRef\":\"consent-" + captureId + "\"}";
        return new MockMultipartFile("metadata", "metadata", "application/json",
                json.getBytes(StandardCharsets.UTF_8));
    }
}

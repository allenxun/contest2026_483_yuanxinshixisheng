package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.care.CareFaceVerifier;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** {@link InsightFaceCareVerifier} 1:1 映射测试（红线：绝不用全库 top1、绝不默认 MATCHED）。 */
class InsightFaceCareVerifierTest {

    private static final byte[] SYNTHETIC_FACE = "fake-face-bytes".getBytes(StandardCharsets.UTF_8);
    private static final UUID MEMBER_ID = UUID.fromString("00000000-0000-0000-0000-0000000000aa");

    private FaceServiceStub stub;
    private JdbcTemplate jdbc;
    private InsightFaceCareVerifier verifier;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
        jdbc = mock(JdbcTemplate.class);
        when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(List.of(new InsightFaceCareVerifier.MemberRef("openvela-mvp", "subj-1")));
        InsightFaceProperties props = new InsightFaceProperties(stub.baseUrl(), "openvela-mvp",
                "FAKE-INTERNAL-TOKEN-DO-NOT-USE", null, 1500, 1500, 0.4);
        verifier = new InsightFaceCareVerifier(new FaceServiceClient(props, new ObjectMapper()),
                jdbc, props.verifyThreshold());
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    @Test
    @DisplayName("verify matched=true → MATCHED，且请求带 namespace/subject_id")
    void matchedIsMatched() {
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.MATCHED);
        String body = new String(stub.last("POST", "/v1/verify").body(), StandardCharsets.UTF_8);
        assertThat(body).contains("openvela-mvp").contains("subj-1");
    }

    @Test
    @DisplayName("verify matched=false → MISMATCH（不默认 MATCHED）")
    void notMatchedIsMismatch() {
        stub.verify(200, "{\"matched\":false,\"similarity\":0.1,\"threshold\":0.4,"
                + "\"request_id\":\"r-mismatch\"}");
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.MISMATCH);
    }

    @Test
    @DisplayName("SUBJECT_NOT_FOUND → CAPABILITY_UNAVAILABLE（无绑定即 fail-closed）")
    void subjectNotFoundIsCapabilityUnavailable() {
        stub.verify(404, FaceServiceStub.errorBody("SUBJECT_NOT_FOUND", false, "r-sub"));
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.CAPABILITY_UNAVAILABLE);
    }

    @Test
    @DisplayName("LIVENESS_UNSUPPORTED → CAPABILITY_UNAVAILABLE")
    void livenessUnsupportedIsCapabilityUnavailable() {
        stub.verify(501, FaceServiceStub.errorBody("LIVENESS_UNSUPPORTED", false, "r-live"));
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.CAPABILITY_UNAVAILABLE);
    }

    @Test
    @DisplayName("NO_FACE → QUALITY_REJECTED")
    void noFaceIsQualityRejected() {
        stub.verify(400, FaceServiceStub.errorBody("NO_FACE", false, "r-nf"));
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.QUALITY_REJECTED);
    }

    @Test
    @DisplayName("5xx → DEPENDENCY_FAILED")
    void serverErrorIsDependencyFailed() {
        stub.verify(503, FaceServiceStub.errorBody("MODEL_UNAVAILABLE", true, "r-dep"));
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.DEPENDENCY_FAILED);
    }

    @Test
    @DisplayName("成员无 face_subject_ref / 不存在 → CAPABILITY_UNAVAILABLE（不调远端）")
    @SuppressWarnings("unchecked")
    void missingMemberBindingIsCapabilityUnavailable() {
        when(jdbc.query(anyString(), any(RowMapper.class), any())).thenReturn(List.of());
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.CAPABILITY_UNAVAILABLE);
        assertThat(stub.requests()).isEmpty();

        when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(List.of(new InsightFaceCareVerifier.MemberRef("openvela-mvp", "  ")));
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.CAPABILITY_UNAVAILABLE);
    }
}

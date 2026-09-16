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

/**
 * {@link InsightFaceCareVerifier} 活体失败映射测试（IMPORTANT 契约冻结）：
 * {@code LIVENESS_NOT_PASSED}（声明支持活体但本次样本未通过/未返回结果）必须映射为
 * 安全结果 {@link CareFaceVerifier.Outcome#CAPABILITY_UNAVAILABLE}，<b>绝不</b> MATCHED。
 */
class InsightFaceCareVerifierLivenessMappingTest {

    private static final byte[] SYNTHETIC_FACE = "fake-face-bytes".getBytes(StandardCharsets.UTF_8);
    private static final UUID MEMBER_ID = UUID.fromString("00000000-0000-0000-0000-0000000000bb");

    private FaceServiceStub stub;
    private InsightFaceCareVerifier verifier;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(List.of(new InsightFaceCareVerifier.MemberRef("openvela-mvp", "subj-1")));
        InsightFaceProperties props = new InsightFaceProperties(stub.baseUrl(), "openvela-mvp",
                "FAKE-INTERNAL-TOKEN-DO-NOT-USE", null, 1500, 1500, 0.4);
        verifier = new InsightFaceCareVerifier(new FaceServiceClient(props, new ObjectMapper()),
                jdbc);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    @Test
    @DisplayName("LIVENESS_NOT_PASSED ⇒ CAPABILITY_UNAVAILABLE（绝不 MATCHED）")
    void livenessNotPassedIsCapabilityUnavailable() {
        stub.verify(501, FaceServiceStub.errorBody("LIVENESS_NOT_PASSED", false, "r-lp"));
        CareFaceVerifier.Outcome outcome = verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE);
        assertThat(outcome).isEqualTo(CareFaceVerifier.Outcome.CAPABILITY_UNAVAILABLE);
        assertThat(outcome).isNotEqualTo(CareFaceVerifier.Outcome.MATCHED);
    }

    @Test
    @DisplayName("LIVENESS_UNSUPPORTED ⇒ CAPABILITY_UNAVAILABLE（既有行为不回归）")
    void livenessUnsupportedStaysCapabilityUnavailable() {
        stub.verify(501, FaceServiceStub.errorBody("LIVENESS_UNSUPPORTED", false, "r-lu"));
        assertThat(verifier.verifyOneToOne("admission", MEMBER_ID, SYNTHETIC_FACE))
                .isEqualTo(CareFaceVerifier.Outcome.CAPABILITY_UNAVAILABLE);
    }
}

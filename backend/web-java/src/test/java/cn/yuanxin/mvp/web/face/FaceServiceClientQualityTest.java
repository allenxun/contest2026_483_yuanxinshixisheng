package cn.yuanxin.mvp.web.face;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** {@link FaceServiceClient#quality} 严格质量块校验测试（契约 §2.2）。全部离线。 */
class FaceServiceClientQualityTest {

    private static final byte[] SYNTHETIC_IMAGE = "fake-quality-bytes".getBytes(StandardCharsets.UTF_8);

    private FaceServiceStub stub;
    private FaceServiceClient client;

    @BeforeEach
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
        client = new FaceServiceClient(new InsightFaceProperties(stub.baseUrl(), "openvela-mvp",
                "FAKE-INTERNAL-TOKEN-DO-NOT-USE", null, 1500, 1500, 0.4), new ObjectMapper());
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    @Test
    @DisplayName("quality 成功：face_count/min_acceptable/liveness.supported（如实）")
    void qualityParsed() {
        FaceQualityView view = client.quality("grant", SYNTHETIC_IMAGE);
        assertThat(view.faceCount()).isEqualTo(1);
        assertThat(view.minAcceptable()).isTrue();
        assertThat(view.reasons()).isEmpty();
        assertThat(view.livenessSupported()).isFalse();
        assertThat(view.requestId()).isEqualTo("req-quality");
    }

    @Test
    @DisplayName("quality：取 largest_face 的质量判定（不是第一张脸）")
    void qualityUsesLargestFace() {
        stub.quality(200, "{\"face_count\":2,\"faces\":["
                + "{\"quality\":{\"min_acceptable\":true},\"largest_face\":false},"
                + "{\"quality\":{\"min_acceptable\":false},\"largest_face\":true}],"
                + "\"liveness\":{\"supported\":false},\"request_id\":\"r-two\"}");
        FaceQualityView view = client.quality("grant", SYNTHETIC_IMAGE);
        assertThat(view.faceCount()).isEqualTo(2);
        assertThat(view.minAcceptable()).isFalse();
    }

    @ParameterizedTest(name = "质量形状违规 #{index}")
    @DisplayName("quality 形状违规 ⇒ MALFORMED_RESPONSE（绝不默认成合格）")
    @ValueSource(strings = {
            "{\"faces\":[{\"quality\":{\"min_acceptable\":true},\"largest_face\":true}],"
                    + "\"liveness\":{\"supported\":false}}",
            "{\"face_count\":1,\"faces\":[],\"liveness\":{\"supported\":false}}",
            "{\"face_count\":1,\"liveness\":{\"supported\":false}}",
            "{\"face_count\":1,\"faces\":[{\"largest_face\":true}],"
                    + "\"liveness\":{\"supported\":false}}",
            "{\"face_count\":-1,\"faces\":[{\"quality\":{\"min_acceptable\":true},\"largest_face\":true}],"
                    + "\"liveness\":{\"supported\":false}}",
            "{\"face_count\":1,\"faces\":[{\"quality\":{\"min_acceptable\":\"yes\"},\"largest_face\":true}],"
                    + "\"liveness\":{\"supported\":false}}",
            "{\"face_count\":1,\"faces\":[{\"quality\":{\"min_acceptable\":true},\"largest_face\":true}]}"
    })
    void qualityShapeViolationsFailClosed(String body) {
        stub.quality(200, body);
        assertThatThrownBy(() -> client.quality("grant", SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).error().code())
                        .isEqualTo("MALFORMED_RESPONSE"));
    }

    @Test
    @DisplayName("QUALITY_INSUFFICIENT(422) ⇒ 抛异常并保留服务码（不静默成合格）")
    void qualityInsufficientThrows() {
        stub.quality(422, FaceServiceStub.errorBody("QUALITY_INSUFFICIENT", false, "r-q"));
        assertThatThrownBy(() -> client.quality("grant", SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).error().code())
                        .isEqualTo("QUALITY_INSUFFICIENT"));
    }
}
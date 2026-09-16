package cn.yuanxin.mvp.web.face;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** {@link FaceServiceClient} 的本地 stub 测试（不发真实人脸、不访问真实服务）。 */
class FaceServiceClientTest {

    private static final byte[] SYNTHETIC_IMAGE = "fake-image-bytes".getBytes(StandardCharsets.UTF_8);
    private static final String FAKE_TOKEN = "FAKE-INTERNAL-TOKEN-DO-NOT-USE";

    private FaceServiceStub stub;
    private FaceServiceClient client;

    @BeforeEach
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
        client = new FaceServiceClient(properties(stub.baseUrl(), 1500, 1500), new ObjectMapper());
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private static InsightFaceProperties properties(String baseUrl, int connect, int read) {
        return new InsightFaceProperties(baseUrl, "openvela-mvp", FAKE_TOKEN, null, connect, read, null);
    }

    @Test
    @DisplayName("health 解析公开端点（liveness.supported=false）")
    void healthParsed() {
        FaceServiceClient.Health health = client.health();
        assertThat(health.ok()).isTrue();
        assertThat(health.modelLoaded()).isTrue();
        assertThat(health.livenessSupported()).isFalse();
    }

    @Test
    @DisplayName("extract 成功返回 face_count；内部 token 随请求发送")
    void extractSuccessAndTokenHeader() {
        FaceServiceClient.ExtractResult result = client.extract(SYNTHETIC_IMAGE);
        assertThat(result.faceCount()).isEqualTo(1);
        assertThat(stub.last("POST", "/v1/extract").internalToken()).isEqualTo(FAKE_TOKEN);
    }

    @Test
    @DisplayName("NO_FACE(400) → 抛异常并携带服务码（不静默成功）")
    void noFaceThrows() {
        stub.extract(400, FaceServiceStub.errorBody("NO_FACE", false, "r-noface"));
        assertThatThrownBy(() -> client.extract(SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> {
                    FaceServiceException e = (FaceServiceException) thrown;
                    assertThat(e.error().code()).isEqualTo("NO_FACE");
                    assertThat(e.error().httpStatus()).isEqualTo(400);
                });
    }

    @Test
    @DisplayName("SUBJECT_NOT_FOUND(404) → CAPABILITY")
    void subjectNotFoundIsCapability() {
        stub.verify(404, FaceServiceStub.errorBody("SUBJECT_NOT_FOUND", false, "r-sub"));
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, "openvela-mvp", "sub-1", null))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.CAPABILITY));
    }

    @Test
    @DisplayName("MODEL_UNAVAILABLE(503) → DEPENDENCY")
    void serviceUnavailableIsDependency() {
        stub.extract(503, FaceServiceStub.errorBody("MODEL_UNAVAILABLE", true, "r-model"));
        assertThatThrownBy(() -> client.extract(SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.DEPENDENCY));
    }

    @Test
    @DisplayName("UNAUTHORIZED(401) → CONFIGURATION")
    void unauthorizedIsConfiguration() {
        stub.extract(401, FaceServiceStub.errorBody("UNAUTHORIZED", false, "r-auth"));
        assertThatThrownBy(() -> client.extract(SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.CONFIGURATION));
    }

    @Test
    @DisplayName("读取超时 → DEPENDENCY（不静默成功）")
    void timeoutIsDependency() {
        stub.delay(1600);
        FaceServiceClient slow = new FaceServiceClient(properties(stub.baseUrl(), 1000, 1000),
                new ObjectMapper());
        assertThatThrownBy(() -> slow.extract(SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.DEPENDENCY));
    }
}

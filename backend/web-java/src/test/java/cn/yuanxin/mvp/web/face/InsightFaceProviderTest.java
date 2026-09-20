package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * {@link InsightFaceProvider} 映射测试（红线 1）：成功检出人脸**绝不**是
 * {@code MATCHED}/{@code RELIABLE_NEW}。含判别力负向断言。
 */
class InsightFaceProviderTest {

    private static final byte[] SYNTHETIC_IMAGE = "fake-face-bytes".getBytes(StandardCharsets.UTF_8);

    private FaceServiceStub stub;
    private InsightFaceProvider provider;

    @BeforeEach
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
        InsightFaceProperties props = new InsightFaceProperties(stub.baseUrl(), "openvela-mvp",
                "FAKE-INTERNAL-TOKEN-DO-NOT-USE", null, 1500, 1500, null);
        provider = new InsightFaceProvider(new FaceServiceClient(props, new ObjectMapper()));
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    @Test
    @DisplayName("红线1：extract 成功检出人脸 → UNCERTAIN，且绝不是 MATCHED/RELIABLE_NEW")
    void extractSuccessIsUncertainNeverMatched() {
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isEqualTo(FaceClassification.UNCERTAIN);
        assertThat(result).isNotEqualTo(FaceClassification.MATCHED);
        assertThat(result).isNotEqualTo(FaceClassification.RELIABLE_NEW);
    }

    @Test
    @DisplayName("NO_FACE → QUALITY_REJECTED")
    void noFaceIsQualityRejected() {
        stub.extract(400, FaceServiceStub.errorBody("NO_FACE", false, "r1"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isEqualTo(FaceClassification.QUALITY_REJECTED);
    }

    @Test
    @DisplayName("MULTI_FACES_AMBIGUOUS → QUALITY_REJECTED")
    void multiFacesIsQualityRejected() {
        stub.extract(400, FaceServiceStub.errorBody("MULTI_FACES_AMBIGUOUS", false, "r2"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isEqualTo(FaceClassification.QUALITY_REJECTED);
    }

    @Test
    @DisplayName("503 → DEPENDENCY_FAILED（绝不视为匹配）")
    void serviceUnavailableIsDependencyFailed() {
        stub.extract(503, FaceServiceStub.errorBody("MODEL_UNAVAILABLE", true, "r3"));
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isEqualTo(FaceClassification.DEPENDENCY_FAILED);
        assertThat(result).isNotEqualTo(FaceClassification.MATCHED);
    }

    @Test
    @DisplayName("401（配置错误）→ DEPENDENCY_FAILED，不静默成功")
    void unauthorizedIsNotSuccess() {
        stub.extract(401, FaceServiceStub.errorBody("UNAUTHORIZED", false, "r4"));
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isNotEqualTo(FaceClassification.MATCHED);
        assertThat(result).isNotEqualTo(FaceClassification.RELIABLE_NEW);
        assertThat(result).isEqualTo(FaceClassification.DEPENDENCY_FAILED);
    }

    @Test
    @DisplayName("判别力：任何 classify 结果都不可能是 MATCHED/RELIABLE_NEW")
    void classifyNeverReturnsMatchedOrReliableNew() {
        stub.extract(200, "{\"face_count\":1,\"request_id\":\"ok\"}");
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isNotIn(FaceClassification.MATCHED, FaceClassification.RELIABLE_NEW);
        stub.extract(503, FaceServiceStub.errorBody("INFERENCE_TIMEOUT", true, "r5"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isNotIn(FaceClassification.MATCHED, FaceClassification.RELIABLE_NEW);
    }
}

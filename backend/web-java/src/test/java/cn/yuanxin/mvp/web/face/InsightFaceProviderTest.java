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
 * {@link InsightFaceProvider} 映射测试（修订红线①）：{@code MATCHED} <b>只</b>来自 namespace
 * 限定的 1:N 搜索命中；"未命中"<b>绝不</b>是 {@code RELIABLE_NEW}。含判别力负向断言。
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

    private static String matchedBody(String subjectRef) {
        return "{\"decision\":\"matched\",\"subject_id\":\"" + subjectRef + "\","
                + "\"similarity\":0.91,\"ambiguous\":false,\"subject_count\":1,"
                + "\"policy_version\":\"search-v1\",\"library_revision\":3,"
                + "\"request_id\":\"r-matched\"}";
    }

    private static String decisionBody(String decision) {
        return "{\"decision\":\"" + decision + "\",\"ambiguous\":false,\"subject_count\":2,"
                + "\"policy_version\":\"search-v1\",\"library_revision\":3,"
                + "\"request_id\":\"r-" + decision + "\"}";
    }

    @Test
    @DisplayName("修订红线①：1:N 搜索 matched → MATCHED（唯一来源），且绝不是 RELIABLE_NEW")
    void searchMatchedIsMatched() {
        stub.search(200, matchedBody("subj-1"));
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isEqualTo(FaceClassification.MATCHED);
        assertThat(result).isNotEqualTo(FaceClassification.RELIABLE_NEW);
        // MATCHED 只能来自搜索命中，不能来自仅 extract。
        assertThat(stub.count("POST", "/search")).isEqualTo(1);
        assertThat(stub.count("POST", "/v1/extract")).isZero();
    }

    @Test
    @DisplayName("修订红线①：no_match → UNCERTAIN，绝不是 MATCHED/RELIABLE_NEW")
    void noMatchIsUncertainNeverReliableNew() {
        stub.search(200, decisionBody("no_match"));
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isEqualTo(FaceClassification.UNCERTAIN);
        assertThat(result).isNotEqualTo(FaceClassification.MATCHED);
        assertThat(result).isNotEqualTo(FaceClassification.RELIABLE_NEW);
    }

    @Test
    @DisplayName("uncertain → UNCERTAIN（绝不 MATCHED/RELIABLE_NEW）")
    void uncertainIsUncertain() {
        stub.search(200, decisionBody("uncertain"));
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isEqualTo(FaceClassification.UNCERTAIN);
        assertThat(result).isNotIn(FaceClassification.MATCHED, FaceClassification.RELIABLE_NEW);
    }

    @Test
    @DisplayName("NO_FACE → QUALITY_REJECTED")
    void noFaceIsQualityRejected() {
        stub.search(400, FaceServiceStub.errorBody("NO_FACE", false, "r1"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isEqualTo(FaceClassification.QUALITY_REJECTED);
    }

    @Test
    @DisplayName("MULTI_FACES_AMBIGUOUS → QUALITY_REJECTED")
    void multiFacesIsQualityRejected() {
        stub.search(400, FaceServiceStub.errorBody("MULTI_FACES_AMBIGUOUS", false, "r2"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isEqualTo(FaceClassification.QUALITY_REJECTED);
    }

    @Test
    @DisplayName("503 → DEPENDENCY_FAILED（绝不视为匹配）")
    void serviceUnavailableIsDependencyFailed() {
        stub.search(503, FaceServiceStub.errorBody("MODEL_UNAVAILABLE", true, "r3"));
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isEqualTo(FaceClassification.DEPENDENCY_FAILED);
        assertThat(result).isNotEqualTo(FaceClassification.MATCHED);
    }

    @Test
    @DisplayName("401（配置错误）→ DEPENDENCY_FAILED，不静默成功")
    void unauthorizedIsNotSuccess() {
        stub.search(401, FaceServiceStub.errorBody("UNAUTHORIZED", false, "r4"));
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isNotEqualTo(FaceClassification.MATCHED);
        assertThat(result).isNotEqualTo(FaceClassification.RELIABLE_NEW);
        assertThat(result).isEqualTo(FaceClassification.DEPENDENCY_FAILED);
    }

    @Test
    @DisplayName("形状违规（非 matched 带 subject_id）→ MALFORMED ⇒ DEPENDENCY_FAILED，绝不 MATCHED")
    void malformedSearchIsDependencyFailed() {
        stub.search(200, "{\"decision\":\"no_match\",\"subject_id\":\"subj-x\","
                + "\"policy_version\":\"search-v1\",\"library_revision\":3,\"request_id\":\"r-bad\"}");
        FaceClassification result = provider.classify("grant", SYNTHETIC_IMAGE);
        assertThat(result).isEqualTo(FaceClassification.DEPENDENCY_FAILED);
        assertThat(result).isNotIn(FaceClassification.MATCHED, FaceClassification.RELIABLE_NEW);
    }

    @Test
    @DisplayName("判别力（加强）：任何 classify 结果都不可能是 RELIABLE_NEW，兜底路径也不产生 MATCHED")
    void classifyNeverReturnsReliableNew() {
        stub.search(200, matchedBody("subj-1"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isNotEqualTo(FaceClassification.RELIABLE_NEW);
        stub.search(200, decisionBody("no_match"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isNotEqualTo(FaceClassification.RELIABLE_NEW);
        stub.search(200, decisionBody("uncertain"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isNotEqualTo(FaceClassification.RELIABLE_NEW);
        stub.search(503, FaceServiceStub.errorBody("INFERENCE_TIMEOUT", true, "r5"));
        assertThat(provider.classify("grant", SYNTHETIC_IMAGE))
                .isNotIn(FaceClassification.MATCHED, FaceClassification.RELIABLE_NEW);
    }
}
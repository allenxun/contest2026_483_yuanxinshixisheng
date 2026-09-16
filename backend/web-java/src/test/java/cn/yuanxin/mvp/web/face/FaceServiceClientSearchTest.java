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

/**
 * {@link FaceServiceClient#search} 严格形状校验与保守三态映射测试（契约 §2.3）。
 * 全部离线：本地 stub、合成字节，绝不联网。
 */
class FaceServiceClientSearchTest {

    private static final byte[] SYNTHETIC_IMAGE = "fake-search-bytes".getBytes(StandardCharsets.UTF_8);
    private static final String NAMESPACE = "openvela-mvp";

    private FaceServiceStub stub;
    private FaceServiceClient client;

    @BeforeEach
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
        client = new FaceServiceClient(new InsightFaceProperties(stub.baseUrl(), NAMESPACE,
                "FAKE-INTERNAL-TOKEN-DO-NOT-USE", null, 1500, 1500, 0.4), new ObjectMapper());
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private static String matched() {
        return "{\"decision\":\"matched\",\"subject_id\":\"subj-1\",\"similarity\":0.91,"
                + "\"ambiguous\":false,\"subject_count\":1,\"policy_version\":\"search-v1\","
                + "\"library_revision\":7,\"request_id\":\"r-matched\"}";
    }

    // ---------- 三态映射 ----------

    @Test
    @DisplayName("matched → MATCHED，携带 subjectRef/similarity/policyVersion/libraryRevision")
    void matchedMapsToMatched() {
        stub.search(200, matched());
        FaceSearchResult result = client.search("grant", SYNTHETIC_IMAGE);
        assertThat(result.decision()).isEqualTo(FaceSearchDecision.MATCHED);
        assertThat(result.matched()).isTrue();
        assertThat(result.subjectRef()).isEqualTo("subj-1");
        assertThat(result.similarity()).isEqualTo(0.91);
        assertThat(result.policyVersion()).isEqualTo("search-v1");
        assertThat(result.libraryRevision()).isEqualTo(7);
        assertThat(result.requestId()).isEqualTo("r-matched");
    }

    @Test
    @DisplayName("no_match → NO_MATCH，subjectRef/similarity 均为 null（构造器强制最小披露）")
    void noMatchMapsToNoMatch() {
        stub.search(200, "{\"decision\":\"no_match\",\"ambiguous\":false,\"subject_count\":0,"
                + "\"policy_version\":\"search-v1\",\"library_revision\":7,\"request_id\":\"r-nm\"}");
        FaceSearchResult result = client.search("grant", SYNTHETIC_IMAGE);
        assertThat(result.decision()).isEqualTo(FaceSearchDecision.NO_MATCH);
        assertThat(result.matched()).isFalse();
        assertThat(result.subjectRef()).isNull();
        assertThat(result.similarity()).isNull();
    }

    @Test
    @DisplayName("uncertain → UNCERTAIN，subjectRef/similarity 均为 null")
    void uncertainMapsToUncertain() {
        stub.search(200, "{\"decision\":\"uncertain\",\"ambiguous\":true,\"subject_count\":2,"
                + "\"policy_version\":\"search-v1\",\"library_revision\":7,\"request_id\":\"r-un\"}");
        FaceSearchResult result = client.search("grant", SYNTHETIC_IMAGE);
        assertThat(result.decision()).isEqualTo(FaceSearchDecision.UNCERTAIN);
        assertThat(result.subjectRef()).isNull();
        assertThat(result.similarity()).isNull();
    }

    @Test
    @DisplayName("wire：search 不传 top_k、不传阈值，且路径为 namespace 限定；内部 token 随请求发送")
    void searchWireShape() {
        stub.search(200, matched());
        client.search("grant", SYNTHETIC_IMAGE);
        FaceServiceStub.Request request = stub.last("POST", "/search");
        assertThat(request).isNotNull();
        assertThat(request.path()).isEqualTo("/v1/namespaces/openvela-mvp/search");
        assertThat(request.internalToken()).isEqualTo("FAKE-INTERNAL-TOKEN-DO-NOT-USE");
        String body = new String(request.body(), StandardCharsets.UTF_8);
        assertThat(body).contains("name=\"image\"").doesNotContain("top_k")
                .doesNotContain("threshold").doesNotContain("require_liveness");
    }

    // ---------- 严格形状校验（契约 §2.3；违规 ⇒ MALFORMED_RESPONSE，绝不返回 MATCHED/NO_MATCH） ----------

    @ParameterizedTest(name = "形状违规 #{index}: {0}")
    @DisplayName("判别力：任一必需键缺失/类型不符/未知 decision/非 matched 带 subject_id ⇒ MALFORMED")
    @ValueSource(strings = {
            // 缺 decision
            "{\"policy_version\":\"search-v1\",\"library_revision\":7,\"request_id\":\"r\"}",
            // 未知 decision
            "{\"decision\":\"maybe\",\"policy_version\":\"search-v1\",\"library_revision\":7,"
                    + "\"request_id\":\"r\"}",
            // matched 缺 subject_id
            "{\"decision\":\"matched\",\"similarity\":0.9,\"policy_version\":\"search-v1\","
                    + "\"library_revision\":7,\"request_id\":\"r\"}",
            // matched 缺 similarity
            "{\"decision\":\"matched\",\"subject_id\":\"subj-1\",\"policy_version\":\"search-v1\","
                    + "\"library_revision\":7,\"request_id\":\"r\"}",
            // matched similarity 非数值
            "{\"decision\":\"matched\",\"subject_id\":\"subj-1\",\"similarity\":\"0.9\","
                    + "\"policy_version\":\"search-v1\",\"library_revision\":7,\"request_id\":\"r\"}",
            // 非 matched 却带 subject_id（服务端契约禁止）
            "{\"decision\":\"no_match\",\"subject_id\":\"subj-1\",\"policy_version\":\"search-v1\","
                    + "\"library_revision\":7,\"request_id\":\"r\"}",
            // 非 matched 却带 subject_id=null（键出现即违约）
            "{\"decision\":\"uncertain\",\"subject_id\":null,\"policy_version\":\"search-v1\","
                    + "\"library_revision\":7,\"request_id\":\"r\"}",
            // 缺 policy_version
            "{\"decision\":\"no_match\",\"library_revision\":7,\"request_id\":\"r\"}",
            // 缺 library_revision
            "{\"decision\":\"no_match\",\"policy_version\":\"search-v1\",\"request_id\":\"r\"}",
            // 缺 request_id
            "{\"decision\":\"no_match\",\"policy_version\":\"search-v1\",\"library_revision\":7}",
            // 不可解析
            "not-json",
            // 非对象
            "[]"
    })
    void shapeViolationsFailClosed(String body) {
        stub.search(200, body);
        assertThatThrownBy(() -> client.search("grant", SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> {
                    FaceServiceException e = (FaceServiceException) thrown;
                    assertThat(e.error().code()).isEqualTo("MALFORMED_RESPONSE");
                    assertThat(e.kind()).isEqualTo(FaceServiceFailureKind.DEPENDENCY);
                });
    }

    @Test
    @DisplayName("超时 ⇒ FaceServiceException(DEPENDENCY)，绝不返回看似成功的默认值")
    void timeoutFailsClosed() {
        stub.delay(1600);
        FaceServiceClient slow = new FaceServiceClient(new InsightFaceProperties(stub.baseUrl(),
                NAMESPACE, "FAKE-INTERNAL-TOKEN-DO-NOT-USE", null, 1000, 1000, 0.4),
                new ObjectMapper());
        assertThatThrownBy(() -> slow.search("grant", SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> {
                    FaceServiceException e = (FaceServiceException) thrown;
                    assertThat(e.kind()).isEqualTo(FaceServiceFailureKind.DEPENDENCY);
                    assertThat(e.error().code()).isNotEqualTo("MATCHED");
                });
    }

    @Test
    @DisplayName("NAMESPACE_NOT_FOUND(404) ⇒ CAPABILITY（不降级成 no_match）")
    void namespaceNotFoundIsCapability() {
        stub.search(404, FaceServiceStub.errorBody("NAMESPACE_NOT_FOUND", false, "r-ns"));
        assertThatThrownBy(() -> client.search("grant", SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.CAPABILITY));
    }

    @Test
    @DisplayName("NO_FACE(400) ⇒ 抛异常（空白图绝不降级成 no_match）")
    void noFaceIsNotNoMatchDecision() {
        stub.search(400, FaceServiceStub.errorBody("NO_FACE", false, "r-nf"));
        assertThatThrownBy(() -> client.search("grant", SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).error().code())
                        .isEqualTo("NO_FACE"));
    }
}
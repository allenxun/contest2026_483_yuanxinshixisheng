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

/**
 * BLOCKER 1 + SUGGESTION 9 判别测试：{@code verifyWithLiveness} 恒定要求活体且响应形状严格校验、
 * 绝不静默降级为 MATCHED/MISMATCH；{@code verifyPhotoOnly} 恰好相反——<b>不</b>发送
 * {@code require_liveness}，是<b>照片比对，无防翻拍能力</b>。
 *
 * <p>用本地 stub / 逐字原始体（{@link FaceServiceStub#verifyRaw}），不发真实人脸、
 * 不访问真实服务。</p>
 */
class FaceServiceClientStrictVerifyTest {

    private static final byte[] SYNTHETIC_IMAGE = "fake-image-bytes".getBytes(StandardCharsets.UTF_8);
    private static final String FAKE_TOKEN = "FAKE-INTERNAL-TOKEN-DO-NOT-USE";
    private static final String NAMESPACE = "openvela-mvp";
    private static final String SUBJECT = "subj-1";

    private FaceServiceStub stub;
    private FaceServiceClient client;

    @BeforeEach
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
        client = new FaceServiceClient(new InsightFaceProperties(stub.baseUrl(), NAMESPACE,
                FAKE_TOKEN, null, 1500, 1500, 0.4), new ObjectMapper());
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    // ---------- BLOCKER 1: 恒定要求活体 ----------

    @Test
    @DisplayName("verifyWithLiveness 恒定发送 require_liveness=true（无开关）")
    void verifyWithLivenessAlwaysRequiresLiveness() {
        client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE);
        String body = new String(stub.last("POST", "/v1/verify").body(), StandardCharsets.UTF_8);
        assertThat(body).contains("name=\"require_liveness\"").contains("true");
    }

    @Test
    @DisplayName("verifyPhotoOnly 不发送 require_liveness（照片比对，无防翻拍能力）")
    void verifyPhotoOnlyDoesNotSendRequireLiveness() {
        client.verifyPhotoOnly("grant", SUBJECT, SYNTHETIC_IMAGE);
        String body = new String(stub.last("POST", "/v1/verify").body(), StandardCharsets.UTF_8);
        assertThat(body).doesNotContain("require_liveness");
        assertThat(body).contains("subj-1");
    }

    @Test
    @DisplayName("extract 不发送 require_liveness（服务端 extract 无该门）")
    void extractDoesNotRequireLiveness() {
        client.extract("grant", SYNTHETIC_IMAGE);
        String body = new String(stub.last("POST", "/v1/extract").body(), StandardCharsets.UTF_8);
        assertThat(body).doesNotContain("require_liveness");
    }

    // ---------- threshold wire 语义逐字未变（构造器去 threshold 参后仍从 properties 读取） ----------

    @Test
    @DisplayName("threshold wire 逐字未变：两种 verify 都随请求发送，取值来自 app.face.insightface.verify-threshold")
    void thresholdComesFromConfiguredProperty() {
        client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE);
        String livenessBody =
                new String(stub.last("POST", "/v1/verify").body(), StandardCharsets.UTF_8);
        assertThat(livenessBody).contains("name=\"threshold\"").contains("0.4");

        client.verifyPhotoOnly("grant", SUBJECT, SYNTHETIC_IMAGE);
        String photoBody =
                new String(stub.last("POST", "/v1/verify").body(), StandardCharsets.UTF_8);
        assertThat(photoBody).contains("name=\"threshold\"").contains("0.4")
                .doesNotContain("require_liveness");
    }

    @Test
    @DisplayName("threshold 未配置（properties=null）时不发送该字段——服务端固定默认值生效")
    void absentConfiguredThresholdIsNotSent() {
        FaceServiceClient noThreshold = new FaceServiceClient(new InsightFaceProperties(
                stub.baseUrl(), NAMESPACE, FAKE_TOKEN, null, 1500, 1500, null), new ObjectMapper());
        noThreshold.verifyPhotoOnly("grant", SUBJECT, SYNTHETIC_IMAGE);
        String body = new String(stub.last("POST", "/v1/verify").body(), StandardCharsets.UTF_8);
        assertThat(body).doesNotContain("threshold");
    }

    // ---------- 照片比对：无需 liveness 段 ----------

    @Test
    @DisplayName("verifyPhotoOnly：无 liveness 段也能解析（照片比对语义，不要求活体）")
    void photoOnlyDoesNotRequireLivenessBlock() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.87,\"threshold\":0.4,"
                + "\"subject_id\":\"subj-1\",\"request_id\":\"r-p\"}");
        PhotoComparisonMatch result = client.verifyPhotoOnly("grant", SUBJECT, SYNTHETIC_IMAGE);
        assertThat(result.matched()).isTrue();
        assertThat(result.similarity()).isEqualTo(0.87);
        assertThat(result.threshold()).isEqualTo(0.4);
        assertThat(result.subjectRef()).isEqualTo(SUBJECT);
        assertThat(result.requestId()).isEqualTo("r-p");
    }

    @Test
    @DisplayName("verifyPhotoOnly：matched 非 boolean / similarity 非有限 ⇒ 失败（不降级）")
    void photoOnlyStrictShapeFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":\"true\",\"similarity\":0.9,\"threshold\":0.4}");
        assertThatThrownBy(() -> client.verifyPhotoOnly("grant", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.DEPENDENCY));

        stub.verifyRaw(200, "{\"matched\":false,\"similarity\":\"0.9\",\"threshold\":0.4}");
        assertThatThrownBy(() -> client.verifyPhotoOnly("grant", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class);
    }

    // ---------- SUGGESTION 9: 严格契约 ----------

    @Test
    @DisplayName("判别力：仅 {\"matched\":true}（缺 similarity/threshold/liveness）必须失败，绝不 MATCHED")
    void matchedOnlyBodyFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> {
                    FaceServiceException e = (FaceServiceException) thrown;
                    assertThat(e.error().code()).isEqualTo("MALFORMED_RESPONSE");
                    assertThat(e.kind()).isEqualTo(FaceServiceFailureKind.DEPENDENCY);
                });
    }

    @Test
    @DisplayName("严格契约：缺 liveness 段 ⇒ 失败（契约失败，非 MATCHED/MISMATCH）")
    void missingLivenessFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.9,\"threshold\":0.4}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.DEPENDENCY));
    }

    @Test
    @DisplayName("严格契约：liveness.supported 非 boolean ⇒ 失败")
    void livenessSupportedWrongTypeFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.9,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":\"yes\"}}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("活体 fail-closed：2xx 却 liveness.supported=false + matched=true ⇒ CAPABILITY，绝不 MATCHED")
    void unsupportedLivenessOn2xxIsCapabilityUnavailable() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.99,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":false,\"reason\":\"no liveness model\"},"
                + "\"subject_id\":\"subj-1\"}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> {
                    FaceServiceException e = (FaceServiceException) thrown;
                    assertThat(e.error().code()).isEqualTo("LIVENESS_UNSUPPORTED");
                    assertThat(e.kind()).isEqualTo(FaceServiceFailureKind.CAPABILITY);
                });
    }

    @Test
    @DisplayName("严格契约：matched 非 JSON boolean ⇒ 失败")
    void matchedWrongTypeFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":\"true\",\"similarity\":0.9,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":false}}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("严格契约：similarity/threshold 缺失或非数值 ⇒ 失败")
    void similarityThresholdMustBeFiniteNumbers() {
        stub.verifyRaw(200, "{\"matched\":false,\"threshold\":0.4,\"liveness\":{\"supported\":false}}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class);

        stub.verifyRaw(200, "{\"matched\":false,\"similarity\":0.1,\"threshold\":\"0.4\","
                + "\"liveness\":{\"supported\":false}}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("严格契约：返回的 subject_id 与请求不一致 ⇒ 失败")
    void subjectIdEchoMismatchFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.9,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":false},\"subject_id\":\"someone-else\"}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("严格契约：不可解析 JSON ⇒ 失败（不降级）")
    void unparseableBodyFailsClosed() {
        stub.verifyRaw(200, "not-json");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("合规响应：全字段齐全 + subject_id echo 一致 ⇒ 正确解析（不默认）")
    void validStrictResponseParsed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.87,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true,\"passed\":true,\"reason\":\"stub-capable\"},"
                + "\"subject_id\":\"subj-1\",\"request_id\":\"r-ok\"}");
        LivenessVerifiedMatch result =
                client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE);
        assertThat(result.matched()).isTrue();
        assertThat(result.similarity()).isEqualTo(0.87);
        assertThat(result.threshold()).isEqualTo(0.4);
        assertThat(result.subjectRef()).isEqualTo(SUBJECT);
        assertThat(result.requestId()).isEqualTo("r-ok");
    }

    @Test
    @DisplayName("合规响应：不返回 subject_id 时允许（仅要求'若返回则须一致'）")
    void absentSubjectIdAllowed() {
        stub.verifyRaw(200, "{\"matched\":false,\"similarity\":0.1,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true,\"passed\":true}}");
        assertThat(client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE).matched())
                .isFalse();
    }

    // ---------- IMPORTANT: liveness.passed 契约冻结 ----------

    @Test
    @DisplayName("契约冻结：supported=true 但缺 passed ⇒ 拒绝（LIVENESS_NOT_PASSED/CAPABILITY），绝不 MATCHED")
    void supportedButMissingPassedFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.99,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true,\"reason\":\"capable\"},\"subject_id\":\"subj-1\"}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> {
                    FaceServiceException e = (FaceServiceException) thrown;
                    assertThat(e.error().code()).isEqualTo("LIVENESS_NOT_PASSED");
                    assertThat(e.error().retryable()).isFalse();
                    assertThat(e.error().httpStatus()).isEqualTo(501);
                    assertThat(e.kind()).isEqualTo(FaceServiceFailureKind.CAPABILITY);
                });
    }

    @Test
    @DisplayName("契约冻结：supported=true 且 passed=false ⇒ 拒绝（绝不因 matched 放行）")
    void supportedButPassedFalseFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.99,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true,\"passed\":false},\"subject_id\":\"subj-1\"}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).error().code())
                        .isEqualTo("LIVENESS_NOT_PASSED"));
    }

    @Test
    @DisplayName("契约冻结：supported=true 且 passed 非 JSON boolean（字符串 \"true\"）⇒ 拒绝")
    void supportedButPassedWrongTypeFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.99,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true,\"passed\":\"true\"},\"subject_id\":\"subj-1\"}");
        assertThatThrownBy(() -> client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).error().code())
                        .isEqualTo("LIVENESS_NOT_PASSED"));
    }

    @Test
    @DisplayName("契约冻结：supported=true + passed=true + matched=true ⇒ MATCHED（正向可达）")
    void supportedPassedAndMatchedIsMatched() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.87,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true,\"passed\":true},\"subject_id\":\"subj-1\"}");
        assertThat(client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE).matched()).isTrue();
    }

    @Test
    @DisplayName("契约冻结：supported=true + passed=true + matched=false ⇒ MISMATCH（不误判 MATCHED）")
    void supportedPassedAndNotMatchedIsMismatch() {
        stub.verifyRaw(200, "{\"matched\":false,\"similarity\":0.1,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true,\"passed\":true},\"subject_id\":\"subj-1\"}");
        assertThat(client.verifyWithLiveness("admission", SUBJECT, SYNTHETIC_IMAGE).matched()).isFalse();
    }
}
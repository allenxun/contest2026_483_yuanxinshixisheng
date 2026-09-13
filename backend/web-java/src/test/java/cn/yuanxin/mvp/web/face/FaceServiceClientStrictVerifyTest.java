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
 * BLOCKER 1 + SUGGESTION 9 判别测试：verify 恒定要求活体，且响应形状严格校验、
 * 绝不静默降级为 MATCHED/MISMATCH。
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
    @DisplayName("verify 恒定发送 require_liveness=true（无开关）")
    void verifyAlwaysRequiresLiveness() {
        client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, 0.4);
        String body = new String(stub.last("POST", "/v1/verify").body(), StandardCharsets.UTF_8);
        assertThat(body).contains("name=\"require_liveness\"").contains("true");
    }

    @Test
    @DisplayName("extract（classify 路径）不发送 require_liveness（服务端 extract 无该门）")
    void extractDoesNotRequireLiveness() {
        client.extract(SYNTHETIC_IMAGE);
        String body = new String(stub.last("POST", "/v1/extract").body(), StandardCharsets.UTF_8);
        assertThat(body).doesNotContain("require_liveness");
    }

    // ---------- SUGGESTION 9: 严格契约 ----------

    @Test
    @DisplayName("判别力：仅 {\"matched\":true}（缺 similarity/threshold/liveness）必须失败，绝不 MATCHED")
    void matchedOnlyBodyFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true}");
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null))
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
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.DEPENDENCY));
    }

    @Test
    @DisplayName("严格契约：liveness.supported 非 boolean ⇒ 失败")
    void livenessSupportedWrongTypeFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.9,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":\"yes\"}}");
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("活体 fail-closed：2xx 却 liveness.supported=false + matched=true ⇒ CAPABILITY，绝不 MATCHED")
    void unsupportedLivenessOn2xxIsCapabilityUnavailable() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.99,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":false,\"reason\":\"no liveness model\"},"
                + "\"subject_id\":\"subj-1\"}");
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, 0.4))
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
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("严格契约：similarity/threshold 缺失或非数值 ⇒ 失败")
    void similarityThresholdMustBeFiniteNumbers() {
        stub.verifyRaw(200, "{\"matched\":false,\"threshold\":0.4,\"liveness\":{\"supported\":false}}");
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null))
                .isInstanceOf(FaceServiceException.class);

        stub.verifyRaw(200, "{\"matched\":false,\"similarity\":0.1,\"threshold\":\"0.4\","
                + "\"liveness\":{\"supported\":false}}");
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("严格契约：返回的 subject_id 与请求不一致 ⇒ 失败")
    void subjectIdEchoMismatchFailsClosed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.9,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":false},\"subject_id\":\"someone-else\"}");
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("严格契约：不可解析 JSON ⇒ 失败（不降级）")
    void unparseableBodyFailsClosed() {
        stub.verifyRaw(200, "not-json");
        assertThatThrownBy(() -> client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null))
                .isInstanceOf(FaceServiceException.class);
    }

    @Test
    @DisplayName("合规响应：全字段齐全 + subject_id echo 一致 ⇒ 正确解析（不默认）")
    void validStrictResponseParsed() {
        stub.verifyRaw(200, "{\"matched\":true,\"similarity\":0.87,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true,\"reason\":\"stub-capable\"},"
                + "\"subject_id\":\"subj-1\",\"request_id\":\"r-ok\"}");
        FaceServiceClient.VerifyResult result = client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, 0.4);
        assertThat(result.matched()).isTrue();
        assertThat(result.similarity()).isEqualTo(0.87);
        assertThat(result.threshold()).isEqualTo(0.4);
        assertThat(result.requestId()).isEqualTo("r-ok");
    }

    @Test
    @DisplayName("合规响应：不返回 subject_id 时允许（仅要求'若返回则须一致'）")
    void absentSubjectIdAllowed() {
        stub.verifyRaw(200, "{\"matched\":false,\"similarity\":0.1,\"threshold\":0.4,"
                + "\"liveness\":{\"supported\":true}}");
        assertThat(client.verify(SYNTHETIC_IMAGE, NAMESPACE, SUBJECT, null).matched()).isFalse();
    }
}

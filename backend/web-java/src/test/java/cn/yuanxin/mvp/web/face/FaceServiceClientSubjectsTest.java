package cn.yuanxin.mvp.web.face;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link FaceServiceClient#register}/{@link FaceServiceClient#get}/{@link FaceServiceClient#delete}
 * 测试（契约 §4.9）。全部离线。
 *
 * <p><b>能力已实现且已测试，但尚无业务流程调用</b>：写 {@code members.face_subject_ref} 属跨包写域，
 * 待总协调裁定（见 {@code backend/handoffs/B-face-java.md}）。</p>
 */
class FaceServiceClientSubjectsTest {

    private static final byte[] SYNTHETIC_IMAGE = "fake-subject-bytes".getBytes(StandardCharsets.UTF_8);
    private static final String NAMESPACE = "openvela-mvp";
    private static final String SUBJECT = "subj-1";

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

    @Test
    @DisplayName("register 成功：解析 subjectRef/createdAt/libraryRevision，wire 带预确定 subject_id 与 on_exists=conflict")
    void registerSuccess() {
        FaceSubjectRegistration registration = client.register("enroll", SUBJECT, SYNTHETIC_IMAGE);
        assertThat(registration.subjectRef()).isEqualTo(SUBJECT);
        assertThat(registration.libraryRevision()).isEqualTo(4);
        assertThat(registration.createdAt()).isEqualTo("2026-01-01T00:00:00+00:00");
        assertThat(registration.requestId()).isEqualTo("req-register");

        FaceServiceStub.Request request = stub.last("POST", "/subjects");
        assertThat(request.path()).isEqualTo("/v1/namespaces/openvela-mvp/subjects");
        String body = new String(request.body(), StandardCharsets.UTF_8);
        assertThat(body).contains("name=\"image\"").contains("subj-1")
                .contains("name=\"on_exists\"").contains("conflict");
    }

    @Test
    @DisplayName("register：subject_id 回显不一致 ⇒ MALFORMED（绝不把别人的主体当成自己的）")
    void registerEchoMismatchFailsClosed() {
        stub.register(200, "{\"subject_id\":\"someone-else\",\"created_at\":\"2026-01-01T00:00:00+00:00\","
                + "\"library_revision\":4,\"request_id\":\"r\"}");
        assertThatThrownBy(() -> client.register("enroll", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).error().code())
                        .isEqualTo("MALFORMED_RESPONSE"));
    }

    @Test
    @DisplayName("register：SUBJECT_ALREADY_EXISTS(409) ⇒ 归类 CONFIGURATION")
    void subjectAlreadyExistsIsConfiguration() {
        stub.register(409, FaceServiceStub.errorBody("SUBJECT_ALREADY_EXISTS", false, "r-already"));
        assertThatThrownBy(() -> client.register("enroll", SUBJECT, SYNTHETIC_IMAGE))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.CONFIGURATION));
    }

    @Test
    @DisplayName("get 成功：返回主体视图")
    void getSuccess() {
        Optional<FaceSubjectView> found = client.get(SUBJECT);
        assertThat(found).isPresent();
        assertThat(found.get().subjectRef()).isEqualTo(SUBJECT);
        assertThat(found.get().libraryRevision()).isEqualTo(4);
    }

    @Test
    @DisplayName("get：404 SUBJECT_NOT_FOUND ⇒ Optional.empty()（不抛）")
    void getNotFoundReturnsEmpty() {
        stub.get(404, FaceServiceStub.errorBody("SUBJECT_NOT_FOUND", false, "r-404"));
        assertThat(client.get(SUBJECT)).isEmpty();
    }

    @Test
    @DisplayName("get：404 NAMESPACE_NOT_FOUND ⇒ Optional.empty()（不存在的 namespace 内也无主体）")
    void getNamespaceNotFoundReturnsEmpty() {
        stub.get(404, FaceServiceStub.errorBody("NAMESPACE_NOT_FOUND", false, "r-ns"));
        assertThat(client.get(SUBJECT)).isEmpty();
    }

    @Test
    @DisplayName("get：503 ⇒ 照常抛 DEPENDENCY（绝不把依赖故障当'不存在'）")
    void getDependencyFailureThrows() {
        stub.get(503, FaceServiceStub.errorBody("MODEL_UNAVAILABLE", true, "r-dep"));
        assertThatThrownBy(() -> client.get(SUBJECT))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.DEPENDENCY));
    }

    @Test
    @DisplayName("delete 成功：deleted=true + libraryRevision")
    void deleteSuccess() {
        FaceSubjectDeletion deletion = client.delete(SUBJECT);
        assertThat(deletion.deleted()).isTrue();
        assertThat(deletion.libraryRevision()).isEqualTo(5);
        assertThat(deletion.requestId()).isEqualTo("req-delete");
    }

    @Test
    @DisplayName("delete 重复删除幂等：第二次 404 ⇒ deleted=false + 未知修订，不抛")
    void deleteRepeatIsIdempotent() {
        FaceSubjectDeletion first = client.delete(SUBJECT);
        assertThat(first.deleted()).isTrue();

        stub.delete(404, FaceServiceStub.errorBody("SUBJECT_NOT_FOUND", false, "r-again"));
        FaceSubjectDeletion second = client.delete(SUBJECT);
        assertThat(second.deleted()).isFalse();
        assertThat(second.libraryRevision())
                .isEqualTo(FaceSubjectDeletion.UNKNOWN_LIBRARY_REVISION);
        assertThat(second.requestId()).isEqualTo("r-again");
    }

    @Test
    @DisplayName("delete：5xx ⇒ 照常抛 DEPENDENCY（绝不误报'已删除'）")
    void deleteDependencyFailureThrows() {
        stub.delete(503, FaceServiceStub.errorBody("MODEL_UNAVAILABLE", true, "r-dep"));
        assertThatThrownBy(() -> client.delete(SUBJECT))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.DEPENDENCY));
    }

    @Test
    @DisplayName("delete：deleted 非 boolean ⇒ MALFORMED")
    void deleteWrongShapeFailsClosed() {
        stub.delete(200, "{\"deleted\":\"true\",\"library_revision\":5,\"request_id\":\"r\"}");
        assertThatThrownBy(() -> client.delete(SUBJECT))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).error().code())
                        .isEqualTo("MALFORMED_RESPONSE"));
    }
}
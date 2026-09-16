package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.identity.ResolvedFaceIdentity;
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
 * {@link InsightFaceIdentityResolver} 测试（契约 §4.7）。全部离线。
 *
 * <p>刻意覆盖"两次搜索"代价：{@code classify} 一次 + {@code resolve} 一次；
 * 本测试断言 resolver 自身只发起<b>一次</b>搜索，且非 MATCHED 分类<b>零</b>远端调用。</p>
 */
class InsightFaceIdentityResolverTest {

    private static final byte[] SYNTHETIC_IMAGE = "fake-resolve-bytes".getBytes(StandardCharsets.UTF_8);

    private FaceServiceStub stub;
    private InsightFaceIdentityResolver resolver;

    @BeforeEach
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
        InsightFaceProperties props = new InsightFaceProperties(stub.baseUrl(), "openvela-mvp",
                "FAKE-INTERNAL-TOKEN-DO-NOT-USE", null, 1500, 1500, null);
        resolver = new InsightFaceIdentityResolver(new FaceServiceClient(props, new ObjectMapper()),
                props);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    @Test
    @DisplayName("classification != MATCHED ⇒ empty，且零远端调用（保守，不浪费推理）")
    void nonMatchedIsEmptyWithoutRemoteCall() {
        for (FaceClassification classification : new FaceClassification[]{
                FaceClassification.UNCERTAIN, FaceClassification.QUALITY_REJECTED,
                FaceClassification.DEPENDENCY_FAILED, FaceClassification.RELIABLE_NEW}) {
            assertThat(resolver.resolve(SYNTHETIC_IMAGE, classification)).isEmpty();
        }
        assertThat(stub.requests()).isEmpty();
    }

    @Test
    @DisplayName("MATCHED + 搜索命中 ⇒ ResolvedFaceIdentity(namespace, subjectRef)；resolver 自身只搜一次")
    void matchedResolvesIdentity() {
        stub.search(200, "{\"decision\":\"matched\",\"subject_id\":\"subj-1\",\"similarity\":0.9,"
                + "\"policy_version\":\"search-v1\",\"library_revision\":3,\"request_id\":\"r\"}");
        Optional<ResolvedFaceIdentity> identity =
                resolver.resolve(SYNTHETIC_IMAGE, FaceClassification.MATCHED);
        assertThat(identity).isPresent();
        assertThat(identity.get().identityNamespace()).isEqualTo("openvela-mvp");
        assertThat(identity.get().faceSubjectRef()).isEqualTo("subj-1");
        assertThat(resolver.identityNamespace()).isEqualTo("openvela-mvp");
        // 第二次搜索的代价：resolver 自身恰好一次搜索（classify 那次由 provider 完成）。
        assertThat(stub.count("POST", "/search")).isEqualTo(1);
    }

    @Test
    @DisplayName("MATCHED 但第二次搜索 no_match ⇒ empty（不一致即保守拒绝，绝不放行）")
    void inconsistentNoMatchIsEmpty() {
        stub.search(200, "{\"decision\":\"no_match\",\"policy_version\":\"search-v1\","
                + "\"library_revision\":3,\"request_id\":\"r\"}");
        assertThat(resolver.resolve(SYNTHETIC_IMAGE, FaceClassification.MATCHED)).isEmpty();
    }

    @Test
    @DisplayName("MATCHED 但第二次搜索 uncertain ⇒ empty（歧义绝不放行）")
    void inconsistentUncertainIsEmpty() {
        stub.search(200, "{\"decision\":\"uncertain\",\"policy_version\":\"search-v1\","
                + "\"library_revision\":3,\"request_id\":\"r\"}");
        assertThat(resolver.resolve(SYNTHETIC_IMAGE, FaceClassification.MATCHED)).isEmpty();
    }

    @Test
    @DisplayName("如实记录：第二次搜索依赖故障按端口契约抛出（调用方负责映射 503）")
    void dependencyFailurePropagates() {
        stub.search(503, FaceServiceStub.errorBody("MODEL_UNAVAILABLE", true, "r-dep"));
        assertThatThrownBy(() -> resolver.resolve(SYNTHETIC_IMAGE, FaceClassification.MATCHED))
                .isInstanceOf(FaceServiceException.class)
                .satisfies(thrown -> assertThat(((FaceServiceException) thrown).kind())
                        .isEqualTo(FaceServiceFailureKind.DEPENDENCY));
    }
}
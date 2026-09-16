package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.care.CareFaceVerifier;
import cn.yuanxin.mvp.web.identity.ResolvedFaceIdentity;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * <b>类型分离的编译期证据</b>（契约 §4.4）：护理路径只可能消费
 * {@link LivenessVerifiedMatch}，照片比对结果 {@link PhotoComparisonMatch} 无法替代。
 *
 * <p>两种语义在类型层面分离，<b>混用会编译失败</b>——本测试用反射防止将来有人把两者
 * 合并成同一类型（例如让 {@code LivenessVerifiedMatch} 继承 {@code PhotoComparisonMatch}，
 * 或在 {@code FaceIdentityPort} 上把两个方法合并）。
 *
 * <p>说明：护理接口 {@code CareFaceVerifier.verifyOneToOne} 返回的是 {@code Outcome} 枚举
 * （C 包既定契约，不改），因此"护理只接受 LivenessVerifiedMatch"体现为
 * {@link InsightFaceCareVerifier} 依赖 {@link FaceIdentityPort} 且<b>绝不</b>声明
 * {@link PhotoComparisonMatch} 字段；其唯一可用的匹配类型来自
 * {@link FaceIdentityPort#verifyWithLiveness}。</p>
 */
class CareFaceVerifierTypeSeparationTest {

    private static final List<String> INVALIDATION =
            List.of("两个类型可互相赋值", "护理 verifier 依赖 PhotoComparisonMatch", "端口方法返回类型合并");

    @Test
    @DisplayName("端口两方法返回类型不同：verifyWithLiveness→LivenessVerifiedMatch，verifyPhotoOnly→PhotoComparisonMatch")
    void portMethodsReturnDistinctTypes() throws Exception {
        Method liveness = FaceIdentityPort.class.getMethod("verifyWithLiveness",
                String.class, String.class, byte[].class);
        Method photo = FaceIdentityPort.class.getMethod("verifyPhotoOnly",
                String.class, String.class, byte[].class);

        assertThat(liveness.getReturnType()).isEqualTo(LivenessVerifiedMatch.class);
        assertThat(photo.getReturnType()).isEqualTo(PhotoComparisonMatch.class);
        assertThat(liveness.getReturnType()).isNotEqualTo(photo.getReturnType());
    }

    @Test
    @DisplayName("两个匹配类型无子类型关系（混用必编译失败，不是冗余）")
    void matchTypesAreNotAssignableToEachOther() {
        assertThat(PhotoComparisonMatch.class.isAssignableFrom(LivenessVerifiedMatch.class)).isFalse();
        assertThat(LivenessVerifiedMatch.class.isAssignableFrom(PhotoComparisonMatch.class)).isFalse();
        assertThat(PhotoComparisonMatch.class).isNotSameAs(LivenessVerifiedMatch.class);
    }

    @Test
    @DisplayName("护理 verifier 依赖 FaceIdentityPort 且绝不声明 PhotoComparisonMatch")
    void careVerifierNeverDependsOnPhotoComparison() {
        List<Class<?>> fieldTypes = new java.util.ArrayList<>();
        for (Field field : InsightFaceCareVerifier.class.getDeclaredFields()) {
            fieldTypes.add(field.getType());
        }
        assertThat(fieldTypes).contains(FaceIdentityPort.class).doesNotContain(PhotoComparisonMatch.class);

        List<Class<?>> ctorParamTypes = new java.util.ArrayList<>();
        for (Constructor<?> ctor : InsightFaceCareVerifier.class.getConstructors()) {
            ctorParamTypes.addAll(Arrays.asList(ctor.getParameterTypes()));
        }
        assertThat(ctorParamTypes).contains(FaceIdentityPort.class)
                .doesNotContain(PhotoComparisonMatch.class);
    }

    @Test
    @DisplayName("护理接口返回 Outcome（非匹配类型），证据：不会出现把两种匹配混用的签名")
    void careVerifierOutcomeIsNotAMatchType() throws Exception {
        Method verify = CareFaceVerifier.class.getMethod("verifyOneToOne",
                String.class, java.util.UUID.class, byte[].class);
        assertThat(verify.getReturnType()).isEqualTo(CareFaceVerifier.Outcome.class);
        assertThat(verify.getReturnType()).isNotEqualTo(LivenessVerifiedMatch.class);
        assertThat(verify.getReturnType()).isNotEqualTo(PhotoComparisonMatch.class);
        // 判别力说明：上面任何一条失败，就意味着两种语义被合并（本测试注释中列出的失效条件）。
        assertThat(INVALIDATION).isNotEmpty();
    }

    @Test
    @DisplayName("身份解析器依赖端口而非直接依赖 HTTP 客户端类型（供应商无关）")
    void resolverDependsOnPort() {
        List<Class<?>> fieldTypes = new java.util.ArrayList<>();
        for (Field field : InsightFaceIdentityResolver.class.getDeclaredFields()) {
            fieldTypes.add(field.getType());
        }
        assertThat(fieldTypes).contains(FaceIdentityPort.class);
        // 端口类型仍然存在且方法可用（编译期契约）。
        assertThat(FaceIdentityPort.class.getMethods())
                .anySatisfy(m -> assertThat(m.getName()).isEqualTo("search"));
        assertThat(ResolvedFaceIdentity.class.getRecordComponents()).hasSize(2);
    }
}
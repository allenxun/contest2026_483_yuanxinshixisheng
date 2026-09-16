package cn.yuanxin.mvp.web.face;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * 冻结类型契约的单元测试（契约 §2.1 / §2.3）：字段顺序、构造器强制约束，以及
 * {@link FaceSearchDecision} <b>刻意没有</b> {@code RELIABLE_NEW} 取值。
 */
class FaceServiceTypesTest {

    private static List<String> components(Class<?> type) {
        return Arrays.stream(type.getRecordComponents())
                .map(rc -> rc.getName())
                .toList();
    }

    @Test
    @DisplayName("六个辅助视图类型的 record 组件顺序与契约一致（顺序即构造顺序）")
    void viewComponentOrderMatchesContract() {
        assertThat(components(FaceHealthView.class)).containsExactly(
                "status", "modelVersion", "modelLoaded", "livenessSupported", "libraryRevision");
        assertThat(components(FaceExtractView.class)).containsExactly("faceCount", "requestId");
        assertThat(components(FaceQualityView.class)).containsExactly(
                "faceCount", "minAcceptable", "reasons", "livenessSupported", "requestId");
        assertThat(components(FaceSubjectRegistration.class)).containsExactly(
                "subjectRef", "libraryRevision", "createdAt", "requestId");
        assertThat(components(FaceSubjectView.class)).containsExactly(
                "subjectRef", "createdAt", "libraryRevision");
        assertThat(components(FaceSubjectDeletion.class)).containsExactly(
                "deleted", "libraryRevision", "requestId");
    }

    @Test
    @DisplayName("FaceSearchDecision 刻意没有 RELIABLE_NEW（未命中不是可靠新人）")
    void searchDecisionHasNoReliableNew() {
        assertThat(Arrays.stream(FaceSearchDecision.values()).map(Enum::name))
                .containsExactly("MATCHED", "NO_MATCH", "UNCERTAIN")
                .doesNotContain("RELIABLE_NEW");
    }

    @Test
    @DisplayName("FaceSearchResult：MATCHED 必须有非空 subjectRef；非 MATCHED 带 subjectRef 一律拒绝")
    void searchResultEnforcesMinimalDisclosure() {
        FaceSearchResult matched = new FaceSearchResult(FaceSearchDecision.MATCHED, "subj-1",
                0.9, "search-v1", 1L, "r");
        assertThat(matched.matched()).isTrue();

        assertThatThrownBy(() -> new FaceSearchResult(FaceSearchDecision.MATCHED, null,
                0.9, "search-v1", 1L, "r"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new FaceSearchResult(FaceSearchDecision.MATCHED, "  ",
                0.9, "search-v1", 1L, "r"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new FaceSearchResult(FaceSearchDecision.NO_MATCH, "subj-1",
                null, "search-v1", 1L, "r"))
                .isInstanceOf(IllegalArgumentException.class);
        FaceSearchResult noMatch = new FaceSearchResult(FaceSearchDecision.NO_MATCH, null,
                null, "search-v1", 1L, "r");
        assertThat(noMatch.matched()).isFalse();
    }

    @Test
    @DisplayName("视图类型的构造器约束：faceCount>=0、reasons 非 null、subjectRef 非空白")
    void viewConstructorsEnforceConstraints() {
        assertThatThrownBy(() -> new FaceExtractView(-1, "r"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new FaceQualityView(1, true, null, false, "r"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(new FaceQualityView(1, true, List.of(), false, "r").reasons()).isEmpty();
        assertThatThrownBy(() -> new FaceSubjectRegistration(" ", 1L, "t", "r"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new FaceSubjectView(null, "t", 1L))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("PhotoComparisonMatch / LivenessVerifiedMatch 均要求有限数值与非空 subjectRef")
    void matchRecordsRequireFiniteNumbers() {
        assertThatThrownBy(() -> new PhotoComparisonMatch(true, Double.NaN, 0.4, "s", "r"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new LivenessVerifiedMatch(true, 0.9, Double.POSITIVE_INFINITY, "s", "r"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new PhotoComparisonMatch(true, 0.9, 0.4, null, "r"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("FaceSubjectDeletion 的未知修订号是 -1（诚实哨兵，非真实值）")
    void deletionUnknownRevisionSentinel() {
        assertThat(FaceSubjectDeletion.UNKNOWN_LIBRARY_REVISION).isEqualTo(-1L);
    }
}
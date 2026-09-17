package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link ReportNarrationScoreExtractor} 白名单抽取与 fail-closed 单测（无网络）：
 * 缺三项/类型非法/取值越界一律 422 UNSUPPORTED_CONTRACT，details 只含结构性键路径；
 * score/severity 的 null 原样透传；未知键丢弃；区域零转换。
 */
class ReportNarrationScoreExtractorTest {

    private static final String FULL = """
            {
              "schema_version": 1,
              "conclusion": "ignored",
              "metrics": [{"name":"moisture","value":50,"unit":"%"}],
              "pores": {"score": 61, "severity": "mild", "name": "毛孔",
                        "regions": [{"region":"F","name":"额头","score":40,"severity":"ok"}]},
              "spots": {"score": null, "severity": null, "name": "斑点",
                        "regions": [{"region":"L","name":"左脸","score":null,"severity":null}]},
              "surface_gloss": {"score": 67.5, "severity": "none", "name": "光泽",
                        "regions": [{"region":"R","name":"右脸","score":82,"severity":"good"}]}
            }
            """;

    private static ApiException rejected(String payload) {
        return (ApiException) org.assertj.core.api.Assertions.catchThrowable(
                () -> ReportNarrationScoreExtractor.extract(payload));
    }

    @SuppressWarnings("unchecked")
    private static List<String> detail(ApiException failure, String key) {
        Map<String, Object> details = failure.getDetails();
        assertThat(details).isNotNull();
        return (List<String>) details.get(key);
    }

    @Test
    @DisplayName("合法三项：只取三项，score/severity null 原样保留，decimals 不丢精度")
    void extractsThreeGroups() {
        ReportNarrationScores scores = ReportNarrationScoreExtractor.extract(FULL);

        assertThat(scores.pores().name()).isEqualTo("毛孔");
        assertThat(scores.pores().score()).isEqualByComparingTo("61");
        assertThat(scores.pores().regions()).hasSize(1);
        assertThat(scores.pores().regions().get(0).region()).isEqualTo("F");

        assertThat(scores.spots().score()).isNull();
        assertThat(scores.spots().severity()).isNull();
        assertThat(scores.spots().regions().get(0).score()).isNull();

        assertThat(scores.surfaceGloss().score()).isEqualByComparingTo("67.5");
    }

    @Test
    @DisplayName("仅 metrics（当前 Worker 形状）→ 422，missing 恰为三项")
    void metricsOnlyPayloadRejected() {
        ApiException failure = rejected(
                "{\"schema_version\":1,\"conclusion\":\"x\","
                        + "\"metrics\":[{\"name\":\"moisture\",\"value\":50,\"unit\":\"%\"}]}");
        assertThat(failure.getCode()).isEqualTo(ErrorCode.UNSUPPORTED_CONTRACT);
        assertThat(detail(failure, "missing"))
                .containsExactlyInAnyOrder("pores", "spots", "surface_gloss");
    }

    @Test
    @DisplayName("缺任一顶层组 → 422，missing 精确列出")
    void missingGroupRejected() {
        ApiException failure = rejected(
                "{\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]},"
                        + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]}}");
        assertThat(failure.getCode()).isEqualTo(ErrorCode.UNSUPPORTED_CONTRACT);
        assertThat(detail(failure, "missing")).containsExactly("pores");
    }

    @Test
    @DisplayName("顶层组类型不符 / payload 非对象 / 非 JSON → 422 invalid")
    void typeMismatchRejected() {
        assertThat(detail(rejected("{\"pores\":[],\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]},"
                + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]}}"),
                "invalid")).contains("pores");
        assertThat(detail(rejected("[]"), "invalid")).contains("report_payload");
        assertThat(detail(rejected("not json"), "invalid")).contains("report_payload");
    }

    @Test
    @DisplayName("score 越界 / 非 number → 422 invalid 键路径")
    void invalidScoreRejected() {
        assertThat(detail(rejected(group("pores", "\"score\":101")), "invalid"))
                .contains("pores.score");
        assertThat(detail(rejected(group("pores", "\"score\":-1")), "invalid"))
                .contains("pores.score");
        assertThat(detail(rejected(group("pores", "\"score\":\"61\"")), "invalid"))
                .contains("pores.score");
    }

    @Test
    @DisplayName("severity 空白 / 非 string → 422 invalid；缺失视为 null")
    void invalidSeverityRejected() {
        assertThat(detail(rejected(group("pores", "\"severity\":\"   \"")), "invalid"))
                .contains("pores.severity");
        assertThat(detail(rejected(group("pores", "\"severity\":7")), "invalid"))
                .contains("pores.severity");

        ReportNarrationScores scores = ReportNarrationScoreExtractor.extract(group("pores", ""));
        assertThat(scores.pores().severity()).isNull();
    }

    @Test
    @DisplayName("name 缺失/空白 → 422 invalid")
    void invalidNameRejected() {
        assertThat(detail(rejected(group("pores", "\"name\":\"  \"")), "invalid"))
                .contains("pores.name");
    }

    @Test
    @DisplayName("regions 空数组/非数组/缺失 → 422 invalid")
    void invalidRegionsRejected() {
        assertThat(detail(rejected(regionGroup("")), "invalid")).contains("pores.regions");
        assertThat(detail(rejected(
                "{\"pores\":{\"name\":\"n\",\"regions\":\"x\"},"
                        + "\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]},"
                        + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]}}"),
                "invalid")).contains("pores.regions");
        assertThat(detail(rejected(
                "{\"pores\":{\"name\":\"n\"},"
                        + "\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]},"
                        + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]}}"),
                "invalid")).contains("pores.regions");
    }

    @Test
    @DisplayName("区域缺 name / score 非法 → 422 invalid 键路径")
    void invalidRegionRejected() {
        assertThat(detail(rejected(regionGroup("{\"region\":\"F\",\"score\":40}")), "invalid"))
                .contains("pores.regions[0].name");
        assertThat(detail(rejected(regionGroup("{\"region\":\"F\",\"name\":\"额\",\"score\":101}")), "invalid"))
                .contains("pores.regions[0].score");
    }

    @Test
    @DisplayName("未知键丢弃：抽取结果与仅含白名单字段的等价载荷一致")
    void unknownKeysDropped() {
        ReportNarrationScores withUnknown = ReportNarrationScoreExtractor.extract(
                "{\"pores\":{\"name\":\"n\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}],"
                        + "\"debug\":\"x\",\"raw_scores\":[1,2,3]},"
                        + "\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"F\",\"name\":\"额\",\"extra\":9}]},"
                        + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]}}");
        ReportNarrationScores clean = ReportNarrationScoreExtractor.extract(
                "{\"pores\":{\"name\":\"n\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]},"
                        + "\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]},"
                        + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]}}");
        assertThat(withUnknown).isEqualTo(clean);
    }

    @Test
    @DisplayName("区域零转换：区域码与顺序原样保留（不做 F/L/R 映射、不翻转、不重排）")
    void regionsAreNotTransformed() {
        ReportNarrationScores scores = ReportNarrationScoreExtractor.extract(
                "{\"pores\":{\"name\":\"n\",\"regions\":[{\"region\":\"nose\",\"name\":\"鼻部\"},"
                        + "{\"region\":\"perioral\",\"name\":\"口周\"}]},"
                        + "\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"R\",\"name\":\"右脸\"},"
                        + "{\"region\":\"L\",\"name\":\"左脸\"}]},"
                        + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额头\"}]}}");
        assertThat(scores.pores().regions()).extracting(ReportNarrationScores.Region::region)
                .containsExactly("nose", "perioral");
        assertThat(scores.spots().regions()).extracting(ReportNarrationScores.Region::region)
                .containsExactly("R", "L");
    }

    private static String group(String groupName, String extraField) {
        String field = extraField.isEmpty() ? "" : "," + extraField;
        String regions = "\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]";
        return "{"
                + "\"" + groupName + "\":{\"name\":\"n\"," + regions + field + "},"
                + "\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]},"
                + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]}}";
    }

    private static String regionGroup(String regionJson) {
        return "{"
                + "\"pores\":{\"name\":\"n\",\"regions\":[" + regionJson + "]},"
                + "\"spots\":{\"name\":\"s\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]},"
                + "\"surface_gloss\":{\"name\":\"g\",\"regions\":[{\"region\":\"F\",\"name\":\"额\"}]}}";
    }
}

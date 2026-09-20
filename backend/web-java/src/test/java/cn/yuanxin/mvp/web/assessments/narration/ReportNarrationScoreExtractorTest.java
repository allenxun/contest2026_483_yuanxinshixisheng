package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link ReportNarrationScoreExtractor} 白名单抽取与 fail-closed 单测（无网络）：
 * 缺三项/键缺失/类型非法/取值越界一律 422 UNSUPPORTED_CONTRACT，details 只含结构性键路径
 * （missing=键不存在，invalid=键存在但不合法）；显式 null 原样透传；未知键丢弃；区域零转换。
 */
class ReportNarrationScoreExtractorTest {

    private static final String VALID_PORES = "{\"score\":61,\"severity\":\"mild\",\"name\":\"毛孔\","
            + "\"regions\":[{\"region\":\"F\",\"name\":\"额头\",\"score\":40,\"severity\":\"ok\"}]}";
    private static final String VALID_SPOTS = "{\"score\":55,\"severity\":\"moderate\",\"name\":\"斑点\","
            + "\"regions\":[{\"region\":\"L\",\"name\":\"左脸\",\"score\":35,\"severity\":\"mild\"}]}";
    private static final String VALID_GLOSS = "{\"score\":70,\"severity\":\"none\",\"name\":\"光泽\","
            + "\"regions\":[{\"region\":\"R\",\"name\":\"右脸\",\"score\":82,\"severity\":\"good\"}]}";

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

    /** 以给定 pores 对象组装三项合法载荷（spots/surface_gloss 恒合法）。 */
    private static String groups(String poresJson) {
        return "{\"pores\":" + poresJson + ",\"spots\":" + VALID_SPOTS
                + ",\"surface_gloss\":" + VALID_GLOSS + "}";
    }

    /** 合法 pores，末尾追加 extra（用于"重复键覆盖"式非法值用例）。 */
    private static String poresWith(String extraField) {
        return "{\"score\":61,\"severity\":\"mild\",\"name\":\"毛孔\","
                + "\"regions\":[{\"region\":\"F\",\"name\":\"额头\",\"score\":40,\"severity\":\"ok\"}]"
                + (extraField.isEmpty() ? "" : "," + extraField) + "}";
    }

    /** 以给定 region 项组装 pores（其余字段合法）。 */
    private static String regionPayload(String regionJson) {
        return groups("{\"score\":61,\"severity\":\"mild\",\"name\":\"毛孔\",\"regions\":["
                + regionJson + "]}");
    }

    @Test
    @DisplayName("合法三项：只取三项，显式 null 原样保留，decimals 不丢精度")
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
    @DisplayName("显式 null（裁定 A）：组级与 region 级 score/severity 均通过并原样透传为 Java null")
    void explicitNullPassesAndIsPreserved() {
        ReportNarrationScores scores = ReportNarrationScoreExtractor.extract(groups(
                "{\"score\":null,\"severity\":null,\"name\":\"毛孔\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额头\",\"score\":null,\"severity\":null}]}"));

        assertThat(scores.pores().score()).isNull();
        assertThat(scores.pores().severity()).isNull();
        assertThat(scores.pores().regions().get(0).score()).isNull();
        assertThat(scores.pores().regions().get(0).severity()).isNull();
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
                "{\"spots\":" + VALID_SPOTS + ",\"surface_gloss\":" + VALID_GLOSS + "}");
        assertThat(failure.getCode()).isEqualTo(ErrorCode.UNSUPPORTED_CONTRACT);
        assertThat(detail(failure, "missing")).containsExactly("pores");
    }

    @Test
    @DisplayName("组内四键缺失（不是显式 null）→ 422 且进 missing（绝不静默补 null）")
    void missingGroupFieldRejected() {
        assertThat(detail(rejected(groups(
                "{\"severity\":\"mild\",\"name\":\"毛孔\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额头\"}]}")),
                "missing")).contains("pores.score");
        assertThat(detail(rejected(groups(
                "{\"score\":61,\"name\":\"毛孔\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额头\"}]}")),
                "missing")).contains("pores.severity");
        assertThat(detail(rejected(groups(
                "{\"score\":61,\"severity\":\"mild\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额头\"}]}")),
                "missing")).contains("pores.name");
        assertThat(detail(rejected(groups(
                "{\"score\":61,\"severity\":\"mild\",\"name\":\"毛孔\"}")),
                "missing")).contains("pores.regions");
    }

    @Test
    @DisplayName("顶层组类型不符 / payload 非对象 / 非 JSON → 422 invalid")
    void typeMismatchRejected() {
        assertThat(detail(rejected(
                "{\"pores\":[],\"spots\":" + VALID_SPOTS + ",\"surface_gloss\":" + VALID_GLOSS + "}"),
                "invalid")).contains("pores");
        assertThat(detail(rejected("[]"), "invalid")).contains("report_payload");
        assertThat(detail(rejected("not json"), "invalid")).contains("report_payload");
    }

    @Test
    @DisplayName("score 越界 / 非 number → 422 invalid 键路径")
    void invalidScoreRejected() {
        assertThat(detail(rejected(groups(poresWith("\"score\":101"))), "invalid"))
                .contains("pores.score");
        assertThat(detail(rejected(groups(poresWith("\"score\":-1"))), "invalid"))
                .contains("pores.score");
        assertThat(detail(rejected(groups(poresWith("\"score\":\"61\""))), "invalid"))
                .contains("pores.score");
    }

    @Test
    @DisplayName("severity 空白 / 非 string → 422 invalid（缺键另由 missing 用例覆盖）")
    void invalidSeverityRejected() {
        assertThat(detail(rejected(groups(poresWith("\"severity\":\"   \""))), "invalid"))
                .contains("pores.severity");
        assertThat(detail(rejected(groups(poresWith("\"severity\":7"))), "invalid"))
                .contains("pores.severity");
    }

    @Test
    @DisplayName("name 空白 → 422 invalid")
    void invalidNameRejected() {
        assertThat(detail(rejected(groups(poresWith("\"name\":\"  \""))), "invalid"))
                .contains("pores.name");
    }

    @Test
    @DisplayName("regions 空数组/非数组 → 422 invalid；regions 缺失 → 422 missing")
    void invalidRegionsRejected() {
        assertThat(detail(rejected(regionPayload("")), "invalid")).contains("pores.regions");
        assertThat(detail(rejected(groups(
                "{\"score\":61,\"severity\":\"mild\",\"name\":\"毛孔\",\"regions\":\"x\"}")),
                "invalid")).contains("pores.regions");
        assertThat(detail(rejected(groups(
                "{\"score\":61,\"severity\":\"mild\",\"name\":\"毛孔\"}")),
                "missing")).contains("pores.regions");
    }

    @Test
    @DisplayName("region 项缺 name → missing；region score 非法 → invalid 键路径")
    void invalidRegionRejected() {
        assertThat(detail(rejected(regionPayload("{\"region\":\"F\",\"score\":40,\"severity\":\"ok\"}")),
                "missing")).contains("pores.regions[0].name");
        assertThat(detail(rejected(regionPayload(
                "{\"region\":\"F\",\"name\":\"额\",\"score\":101,\"severity\":\"ok\"}")),
                "invalid")).contains("pores.regions[0].score");
    }

    @Test
    @DisplayName("region 项缺 score / 缺 severity → 422 missing（路径形如 pores.regions[0].score）")
    void regionMissingFieldRejected() {
        assertThat(detail(rejected(regionPayload("{\"region\":\"F\",\"name\":\"额头\",\"severity\":\"ok\"}")),
                "missing")).contains("pores.regions[0].score");
        assertThat(detail(rejected(regionPayload("{\"region\":\"F\",\"name\":\"额头\",\"score\":40}")),
                "missing")).contains("pores.regions[0].severity");
    }

    @Test
    @DisplayName("未知键丢弃：抽取结果与仅含白名单字段的等价载荷一致")
    void unknownKeysDropped() {
        ReportNarrationScores withUnknown = ReportNarrationScoreExtractor.extract(
                "{\"pores\":{\"score\":61,\"severity\":\"mild\",\"name\":\"n\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额\",\"score\":40,\"severity\":\"ok\"}],"
                        + "\"debug\":\"x\",\"raw_scores\":[1,2,3]},"
                        + "\"spots\":{\"score\":55,\"severity\":\"moderate\",\"name\":\"s\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额\",\"score\":40,\"severity\":\"ok\","
                        + "\"extra\":9}]},"
                        + "\"surface_gloss\":" + VALID_GLOSS + "}");
        ReportNarrationScores clean = ReportNarrationScoreExtractor.extract(
                "{\"pores\":{\"score\":61,\"severity\":\"mild\",\"name\":\"n\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额\",\"score\":40,\"severity\":\"ok\"}]},"
                        + "\"spots\":{\"score\":55,\"severity\":\"moderate\",\"name\":\"s\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额\",\"score\":40,\"severity\":\"ok\"}]},"
                        + "\"surface_gloss\":" + VALID_GLOSS + "}");
        assertThat(withUnknown).isEqualTo(clean);
    }

    @Test
    @DisplayName("区域零转换：区域码与顺序原样保留（不做 F/L/R 映射、不翻转、不重排）")
    void regionsAreNotTransformed() {
        ReportNarrationScores scores = ReportNarrationScoreExtractor.extract(
                "{\"pores\":{\"score\":60,\"severity\":\"mild\",\"name\":\"n\","
                        + "\"regions\":[{\"region\":\"nose\",\"name\":\"鼻部\",\"score\":50,\"severity\":\"ok\"},"
                        + "{\"region\":\"perioral\",\"name\":\"口周\",\"score\":50,\"severity\":\"ok\"}]},"
                        + "\"spots\":{\"score\":60,\"severity\":\"mild\",\"name\":\"s\","
                        + "\"regions\":[{\"region\":\"R\",\"name\":\"右脸\",\"score\":50,\"severity\":\"ok\"},"
                        + "{\"region\":\"L\",\"name\":\"左脸\",\"score\":50,\"severity\":\"ok\"}]},"
                        + "\"surface_gloss\":" + VALID_GLOSS + "}");
        assertThat(scores.pores().regions()).extracting(ReportNarrationScores.Region::region)
                .containsExactly("nose", "perioral");
        assertThat(scores.spots().regions()).extracting(ReportNarrationScores.Region::region)
                .containsExactly("R", "L");
    }

    @Test
    @DisplayName("缺键与显式 null 判定互斥：显式 null 通过、缺键 422（回归守卫）")
    void missingVersusExplicitNullAreDistinct() {
        // 显式 null 通过。
        ReportNarrationScores explicitNull = ReportNarrationScoreExtractor.extract(groups(
                "{\"score\":null,\"severity\":null,\"name\":\"n\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额\",\"score\":null,\"severity\":null}]}"));
        assertThat(explicitNull.pores().score()).isNull();
        // 缺 score 键 → 422 missing。
        ApiException failure = rejected(groups(
                "{\"severity\":null,\"name\":\"n\","
                        + "\"regions\":[{\"region\":\"F\",\"name\":\"额\",\"score\":null,\"severity\":null}]}"));
        assertThat(failure.getCode()).isEqualTo(ErrorCode.UNSUPPORTED_CONTRACT);
        assertThat(detail(failure, "missing")).contains("pores.score");
    }
}

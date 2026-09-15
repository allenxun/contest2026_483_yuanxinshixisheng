package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.config.NonProductionCondition;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Conditional;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * MOCK 联调数据/文案生成器——固定数据，非正式算法结果，不调用算法/RAG/AI，
 * 不读取密钥；仅供报告播报 SSE 联调。
 *
 * <p>本类不含任何计时器、延迟或线程：固定区域分数在构造时一次算出，播报文案按
 * 固定模板程序化拼接。仅非生产环境生效
 * （{@link NonProductionCondition}）；生产环境该 bean 缺席，
 * 控制器以 {@code DEPENDENCY_UNAVAILABLE} fail-closed。</p>
 *
 * <p>区域分数为对应区域 O/P/D 三项 {@code score} 的算术平均值（四舍五入
 * HALF_UP 到整数）；区域固定顺序 F、L、R、C，展示名依次为额头、左脸、右脸、下巴。
 * 本生成器是联调替身，<strong>不得</strong>作为正式算法/RAG/AI 结果使用。</p>
 */
@Component
@Conditional(NonProductionCondition.class)
public class MockReportNarrationGenerator {

    /** 固定 MOCK 区域数据（联调专用；非正式算法结果）。 */
    static final String MOCK_REGION_JSON =
            "{\"regions\":{"
                    + "\"F\":{\"O\":{\"score\":40,\"label\":\"较明显\"},"
                    + "\"P\":{\"score\":62,\"label\":\"轻度\"},"
                    + "\"D\":{\"score\":81,\"label\":\"未见明显\"}},"
                    + "\"L\":{\"O\":{\"score\":35,\"label\":\"较明显\"},"
                    + "\"P\":{\"score\":28,\"label\":\"较明显\"},"
                    + "\"D\":{\"score\":55,\"label\":\"中度\"}},"
                    + "\"R\":{\"O\":{\"score\":70,\"label\":\"轻度\"},"
                    + "\"P\":{\"score\":82,\"label\":\"未见明显\"},"
                    + "\"D\":{\"score\":50,\"label\":\"中度\"}},"
                    + "\"C\":{\"O\":{\"score\":20,\"label\":\"显著\"},"
                    + "\"P\":{\"score\":50,\"label\":\"中度\"},"
                    + "\"D\":{\"score\":65,\"label\":\"轻度\"}}"
                    + "}}";

    /** 区域固定展示顺序（F→L→R→C）。 */
    private static final List<String> REGION_ORDER = List.of("F", "L", "R", "C");

    /** 区域固定展示名。 */
    private static final Map<String, String> REGION_NAMES = Map.of(
            "F", "额头",
            "L", "左脸",
            "R", "右脸",
            "C", "下巴");

    /** 播报第一句模板：四个区域名。 */
    private static final String SENTENCE_ONE_TEMPLATE = "本次完成%s、%s、%s和%s四个区域的皮肤检测。";

    /** 播报第二句模板：区域名 + 计算所得分数，交替出现。 */
    private static final String SENTENCE_TWO_TEMPLATE = "%s%s分，%s%s分，%s%s分，%s%s分。";

    private final String narrationText;
    private final List<String> deltaChunks;

    public MockReportNarrationGenerator(ObjectMapper objectMapper) {
        Map<String, Integer> scores = computeRegionScores(objectMapper);

        String fName = REGION_NAMES.get("F");
        String lName = REGION_NAMES.get("L");
        String rName = REGION_NAMES.get("R");
        String cName = REGION_NAMES.get("C");

        String sentenceOne = String.format(SENTENCE_ONE_TEMPLATE, fName, lName, rName, cName);
        String sentenceTwo = String.format(SENTENCE_TWO_TEMPLATE,
                fName, scores.get("F"),
                lName, scores.get("L"),
                rName, scores.get("R"),
                cName, scores.get("C"));

        this.deltaChunks = List.of(sentenceOne, sentenceTwo);
        this.narrationText = sentenceOne + sentenceTwo;
    }

    /** 完整播报文案（由两个 delta chunk 程序化拼接）。 */
    public String narrationText() {
        return narrationText;
    }

    /** 恰好两个 delta chunk（顺序即下发顺序）。 */
    public List<String> deltaChunks() {
        return deltaChunks;
    }

    /** 解析固定 MOCK JSON，按区域对 O/P/D 分数取算术平均并四舍五入到整数。 */
    private static Map<String, Integer> computeRegionScores(ObjectMapper objectMapper) {
        JsonNode regions;
        try {
            regions = objectMapper.readTree(MOCK_REGION_JSON).path("regions");
        } catch (Exception invalid) {
            throw new IllegalStateException("mock report narration region JSON is invalid", invalid);
        }
        Map<String, Integer> scores = new LinkedHashMap<>();
        for (String region : REGION_ORDER) {
            JsonNode regionNode = regions.path(region);
            int sum = 0;
            int count = 0;
            for (String axis : List.of("O", "P", "D")) {
                sum += regionNode.path(axis).path("score").asInt();
                count++;
            }
            scores.put(region, BigDecimal.valueOf(sum)
                    .divide(BigDecimal.valueOf(count), 0, RoundingMode.HALF_UP)
                    .intValue());
        }
        return scores;
    }
}
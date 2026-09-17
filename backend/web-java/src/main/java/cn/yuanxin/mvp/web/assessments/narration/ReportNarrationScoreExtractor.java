package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 从 T05 {@code report_payload} 抽取并校验 V3 三项评分，输出已白名单化的
 * {@link ReportNarrationScores}。
 *
 * <p><b>输入契约（fail-closed）</b>：顶层必须是 JSON 对象，且<b>同时</b>含
 * {@code pores}/{@code spots}/{@code surface_gloss} 三个键、每个必须是 JSON 对象。
 * 任一缺失/类型不符即抛 {@link ApiException}（{@code UNSUPPORTED_CONTRACT}，HTTP 422、
 * non-retryable）。<b>绝不</b>用 {@code metrics}/{@code conclusion}/{@code description} 等
 * 现有字段伪映射，<b>绝不</b>发空 body，<b>绝不</b>退回 mock 文案。</p>
 *
 * <p><b>恰好四键白名单</b>：每组只序列化 {@code score}/{@code severity}/{@code name}/{@code regions}，
 * 每个 region 只序列化 {@code region}/{@code name}/{@code score}/{@code severity}。未知键丢弃，
 * 但会 {@code log.warn} 记录<b>被丢弃的键名</b>（组名 + 键名，<b>绝不记录值</b>）以便发现上游契约漂移。</p>
 *
 * <p><b>键缺失 vs 显式 null（必须区分）</b>：组级与 region 级的四键<b>必须存在</b>（{@code has(key)}）。
 * <b>缺键</b> → 键路径进 {@code details.missing}（例如 {@code pores.score}、
 * {@code pores.regions[0].score}）；<b>显式 JSON {@code null}</b> → 映射为 Java {@code null} 并原样透传
 * （裁定 A，绝不 coerce 成 0）。二者语义不同：缺键代表上游未提供该评分，显式 null 代表上游明确声明"无值"。
 * 两类问题任一非空即 422 fail-closed，{@code details} 只含结构性键路径（{@code missing}/{@code invalid}），
 * 绝不含任何评分值、区域值或报告内容。{@code invalid} = 键存在但类型/取值/空白不合法。</p>
 *
 * <p><b>裁定 A（{@code score=null}）</b>：V3 明确 score 可为 null，且任务书要求接受/拒绝以正式
 * AI 合同与真实响应为准、不一致则回报、不猜值。在无法访问真实 AI（无凭据）的前提下，唯一不编造的
 * 做法是<b>原样透传 null</b>：拒绝会破坏合法报告，coerce 成 0 会伪造数据。null 的可接受性尚未经
 * 真实 AI 确认；若真实服务拒绝 null，由 root 联调暴露后回报总协调，<b>不在 Java 侧擅自改为拒绝或补值</b>。</p>
 *
 * <p><b>裁定 B（regions 左右/区域码）</b>：本抽取器<b>零语义转换</b>——不改区域名、不做左右翻转、
 * 不做 {@code 100-score} 反转、不重排、不聚合、不补默认值，V3 的 {@code regions} <b>原样</b>组装进
 * AI body。任务书明令：若 AI 实测要求 F/L/R 或本人左右定义而非原始 V3 regions，停止转换并报告差异。
 * D 的 {@code weijing_mapping.py} 对<b>另一个</b> use-case（plan）做了 {@code 100-score} 反转与
 * {@code F/L/R/C} 区域码映射，且其注释自陈未经生产批准 ⇒ <b>本实现刻意不照抄</b>。</p>
 *
 * <p>与 {@code gimbalai} 的 codes/parser 同源纪律、刻意不共享。</p>
 */
final class ReportNarrationScoreExtractor {

    private static final Logger log = LoggerFactory.getLogger(ReportNarrationScoreExtractor.class);

    private static final ObjectMapper MAPPER = new ObjectMapper();

    static final String PAYLOAD_PATH = "report_payload";

    private static final List<String> GROUPS = List.of("pores", "spots", "surface_gloss");
    private static final Set<String> GROUP_KEYS = Set.of("score", "severity", "name", "regions");
    private static final Set<String> REGION_KEYS = Set.of("region", "name", "score", "severity");
    private static final BigDecimal MAX_SCORE = BigDecimal.valueOf(100);

    private static final String MESSAGE =
            "report payload does not satisfy the required three-group score contract";

    private ReportNarrationScoreExtractor() {
    }

    /**
     * @param reportPayload T05 {@code report_payload::text}
     * @return 已校验、已白名单化的三项评分
     * @throws ApiException {@code UNSUPPORTED_CONTRACT}（422）；{@code details} 只含结构性键路径
     */
    static ReportNarrationScores extract(String reportPayload) {
        List<String> missing = new ArrayList<>();
        List<String> invalid = new ArrayList<>();

        JsonNode root = parse(reportPayload, invalid);
        if (root == null) {
            throw fail(missing, invalid);
        }

        Map<String, ReportNarrationScores.ScoreGroup> groups = new LinkedHashMap<>();
        for (String group : GROUPS) {
            ReportNarrationScores.ScoreGroup parsed = group(root, group, missing, invalid);
            if (parsed != null) {
                groups.put(group, parsed);
            }
        }
        if (!missing.isEmpty() || !invalid.isEmpty()) {
            throw fail(missing, invalid);
        }
        return new ReportNarrationScores(
                groups.get("pores"), groups.get("spots"), groups.get("surface_gloss"));
    }

    private static JsonNode parse(String reportPayload, List<String> invalid) {
        if (reportPayload == null || reportPayload.isBlank()) {
            invalid.add(PAYLOAD_PATH);
            return null;
        }
        try {
            JsonNode root = MAPPER.readTree(reportPayload);
            if (root == null || !root.isObject()) {
                invalid.add(PAYLOAD_PATH);
                return null;
            }
            return root;
        } catch (Exception unparseable) {
            invalid.add(PAYLOAD_PATH);
            return null;
        }
    }

    private static ReportNarrationScores.ScoreGroup group(JsonNode root, String groupName,
                                                          List<String> missing, List<String> invalid) {
        JsonNode node = root.get(groupName);
        if (node == null) {
            missing.add(groupName);
            return null;
        }
        if (!node.isObject()) {
            invalid.add(groupName);
            return null;
        }
        warnUnknownKeys(groupName, node, GROUP_KEYS);

        int invalidBefore = invalid.size();
        int missingBefore = missing.size();
        BigDecimal score = readScore(node, "score", groupName + ".score", missing, invalid);
        String severity = readSeverity(node, "severity", groupName + ".severity", missing, invalid);
        String name = readRequiredText(node, "name", groupName + ".name", missing, invalid);
        List<ReportNarrationScores.Region> regions =
                readRegions(node, groupName, missing, invalid);
        if (invalid.size() != invalidBefore || missing.size() != missingBefore
                || name == null || regions == null) {
            return null;
        }
        return new ReportNarrationScores.ScoreGroup(score, severity, name, regions);
    }

    private static List<ReportNarrationScores.Region> readRegions(JsonNode node, String groupName,
                                                                  List<String> missing,
                                                                  List<String> invalid) {
        if (!node.has("regions")) {
            missing.add(groupName + ".regions");
            return null;
        }
        JsonNode regionsNode = node.get("regions");
        if (regionsNode.isNull() || !regionsNode.isArray() || regionsNode.isEmpty()) {
            invalid.add(groupName + ".regions");
            return null;
        }
        List<ReportNarrationScores.Region> regions = new ArrayList<>();
        for (int i = 0; i < regionsNode.size(); i++) {
            JsonNode region = regionsNode.get(i);
            String path = groupName + ".regions[" + i + "]";
            if (!region.isObject()) {
                invalid.add(path);
                continue;
            }
            warnUnknownKeys(path, region, REGION_KEYS);
            String regionCode = readRequiredText(region, "region", path + ".region", missing, invalid);
            String regionName = readRequiredText(region, "name", path + ".name", missing, invalid);
            BigDecimal regionScore = readScore(region, "score", path + ".score", missing, invalid);
            String regionSeverity =
                    readSeverity(region, "severity", path + ".severity", missing, invalid);
            if (regionCode != null && regionName != null) {
                regions.add(new ReportNarrationScores.Region(
                        regionCode, regionName, regionScore, regionSeverity));
            }
        }
        if (regions.isEmpty()) {
            invalid.add(groupName + ".regions");
            return null;
        }
        return regions;
    }

    /**
     * {@code score}：键<b>必须存在</b>；显式 {@code null} → Java {@code null}（裁定 A，原样透传，
     * 绝不 coerce 成 0）；number 且 0–100 保留；其它类型/越界 → {@code invalid}；缺键 → {@code missing}。
     */
    private static BigDecimal readScore(JsonNode parent, String key, String path,
                                        List<String> missing, List<String> invalid) {
        if (!parent.has(key)) {
            missing.add(path);
            return null;
        }
        JsonNode node = parent.get(key);
        if (node.isNull()) {
            return null;
        }
        if (!node.isNumber()) {
            invalid.add(path);
            return null;
        }
        BigDecimal value = node.decimalValue();
        if (value.compareTo(BigDecimal.ZERO) < 0 || value.compareTo(MAX_SCORE) > 0) {
            invalid.add(path);
            return null;
        }
        return value;
    }

    /**
     * {@code severity}：键<b>必须存在</b>；显式 {@code null} → Java {@code null}（原样透传）；
     * 非空白 string 保留；其它类型/空白 → {@code invalid}；缺键 → {@code missing}。
     */
    private static String readSeverity(JsonNode parent, String key, String path,
                                       List<String> missing, List<String> invalid) {
        if (!parent.has(key)) {
            missing.add(path);
            return null;
        }
        JsonNode node = parent.get(key);
        if (node.isNull()) {
            return null;
        }
        if (!node.isTextual() || node.asText().isBlank()) {
            invalid.add(path);
            return null;
        }
        return node.asText();
    }

    /**
     * {@code name}/{@code region} 等必需文本：键<b>必须存在</b>（缺键 → {@code missing}）；
     * 非空白 string 保留；其它类型/空白（含显式 null）→ {@code invalid}。
     */
    private static String readRequiredText(JsonNode parent, String key, String path,
                                           List<String> missing, List<String> invalid) {
        if (!parent.has(key)) {
            missing.add(path);
            return null;
        }
        JsonNode node = parent.get(key);
        if (!node.isTextual() || node.asText().isBlank()) {
            invalid.add(path);
            return null;
        }
        return node.asText();
    }

    /** 只记被丢弃的<b>键名</b>（组/区域路径 + 键名）；绝不记录值。 */
    private static void warnUnknownKeys(String path, JsonNode object, Set<String> allowed) {
        object.fieldNames().forEachRemaining(key -> {
            if (!allowed.contains(key)) {
                log.warn("report narration payload dropped unknown key path={}.{}", path, key);
            }
        });
    }

    private static ApiException fail(List<String> missing, List<String> invalid) {
        Map<String, Object> details = new LinkedHashMap<>();
        if (!missing.isEmpty()) {
            details.put("missing", List.copyOf(missing));
        }
        if (!invalid.isEmpty()) {
            details.put("invalid", List.copyOf(invalid));
        }
        return new ApiException(ErrorCode.UNSUPPORTED_CONTRACT, MESSAGE, details);
    }
}

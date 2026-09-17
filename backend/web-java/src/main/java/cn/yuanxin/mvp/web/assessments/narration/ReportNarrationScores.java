package cn.yuanxin.mvp.web.assessments.narration;

import java.math.BigDecimal;
import java.util.List;

/**
 * 已校验、已白名单化的 T05 {@code report_payload} 三项评分（V3 形状）。
 *
 * <p>只含 AI body 所需的三个顶层对象 {@code pores}/{@code spots}/{@code surface_gloss}；
 * 每组只保留白名单四键 {@code score}/{@code severity}/{@code name}/{@code regions}。</p>
 *
 * <p><b>零语义转换</b>：区域名、区域顺序、左右口径、分数高低方向全部原样保留——不改名、
 * 不翻转左右、不做 {@code 100-score} 反转、不重排、不聚合、不补默认值。详见
 * {@link ReportNarrationScoreExtractor} 的裁定说明。</p>
 *
 * <p><b>score 可为 null</b>：原样透传为 JSON {@code null}（既拒绝会破坏合法报告，
 * coerce 成 0 会伪造数据）；其可接受性尚未经真实 AI 确认。severity 同理可为 null。</p>
 *
 * @param pores       毛孔组
 * @param spots       斑点组
 * @param surfaceGloss 表面光泽组（序列化键名为 {@code surface_gloss}）
 */
public record ReportNarrationScores(ScoreGroup pores, ScoreGroup spots, ScoreGroup surfaceGloss) {

    public ReportNarrationScores {
        pores = requireGroup(pores, "pores");
        spots = requireGroup(spots, "spots");
        surfaceGloss = requireGroup(surfaceGloss, "surface_gloss");
    }

    /** 单项评分组：白名单四键 {@code score}/{@code severity}/{@code name}/{@code regions}。 */
    public record ScoreGroup(BigDecimal score, String severity, String name, List<Region> regions) {

        public ScoreGroup {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("report narration score group name is required");
            }
            if (regions == null || regions.isEmpty()) {
                throw new IllegalArgumentException("report narration score group regions are required");
            }
            regions = List.copyOf(regions);
        }
    }

    /**
     * 区域项：白名单四键 {@code region}/{@code name}/{@code score}/{@code severity}。
     * {@code region} 为原始区域码/名（零转换），{@code name} 为原始展示名。
     */
    public record Region(String region, String name, BigDecimal score, String severity) {

        public Region {
            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException("report narration region code is required");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("report narration region name is required");
            }
        }
    }

    private static ScoreGroup requireGroup(ScoreGroup group, String key) {
        if (group == null) {
            throw new IllegalArgumentException("report narration group is required: " + key);
        }
        return group;
    }
}

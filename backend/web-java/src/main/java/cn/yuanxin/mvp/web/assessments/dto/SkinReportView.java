package cn.yuanxin.mvp.web.assessments.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;
import java.util.Map;

/**
 * M3-A05 报告受控投影（openapi components.schemas.SkinReportView）。
 * 只从冻结 report_payload 白名单投影；model_info 与未知键绝不输出。
 * brief 视图不暴露 memberId/metrics/description：memberId/description 合同
 * 允许 null（nullable: true），metrics 合同为非 nullable 的 array，故 brief
 * 时整字段省略（{@code @JsonInclude(NON_NULL)}）。
 */
public record SkinReportView(
        String reportId,
        String view,
        String memberId,
        String reportReadyAt,
        String conclusion,
        @JsonInclude(JsonInclude.Include.NON_NULL) List<Map<String, Object>> metrics,
        String description,
        List<SkinReportImage> images,
        String planStatus) {

    /** images[] 元素：同源鉴权代理 contentUrl。 */
    public record SkinReportImage(String mediaId, String contentUrl) {
    }
}

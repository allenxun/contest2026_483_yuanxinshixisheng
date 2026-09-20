package cn.yuanxin.mvp.web.assessments.dto;

import com.fasterxml.jackson.databind.JsonNode;

/** M3-A04 items 元素（openapi components.schemas.SkinReportListItem）。 */
public record SkinReportListItem(
        String reportId,
        String reportReadyAt,
        JsonNode reportSummary) {
}

package cn.yuanxin.mvp.web.assessments.dto;

import java.util.List;

/**
 * M3-A03 输出（openapi components.schemas.AssessmentTaskView）。
 * failureCode/retryable 为有界公开投影；failure_detail 原文绝不外泄。
 * reportId 仅在 report_ready 时给出；planAvailability 为关联方案的
 * generation_status（或 null）。
 */
public record AssessmentTaskView(
        String taskId,
        String status,
        String photoVersion,
        List<String> requiredViews,
        String failureCode,
        Boolean retryable,
        String reportId,
        String planAvailability) {
}

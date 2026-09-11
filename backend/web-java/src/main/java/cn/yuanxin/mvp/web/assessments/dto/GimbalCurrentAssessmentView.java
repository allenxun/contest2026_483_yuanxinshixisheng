package cn.yuanxin.mvp.web.assessments.dto;

/**
 * M3-A06 输出（openapi components.schemas.GimbalCurrentAssessmentView）：
 * currentAssessment 可空；currentAssessmentRevision 为 bigint 字符串。
 */
public record GimbalCurrentAssessmentView(
        CurrentAssessment currentAssessment,
        String currentAssessmentRevision) {

    public record CurrentAssessment(
            String taskId,
            String status,
            String photoVersion,
            String reportId) {
    }
}

package cn.yuanxin.mvp.web.assessments.dto;

/**
 * M3-A01/M3-A02 受理输出（openapi components.schemas.AssessmentTaskAccepted）：
 * taskId、status=queued、photoVersion、currentAssessmentRevision（bigint 字符串）。
 * 重放响应 currentAssessmentRevision 为 null（只投影 T13 存储摘要）。
 */
public record AssessmentTaskAccepted(
        String taskId,
        String status,
        String photoVersion,
        String currentAssessmentRevision) {
}

package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.assessments.dto.AssessmentTaskView;
import cn.yuanxin.mvp.web.assessments.dto.GimbalCurrentAssessmentView;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

/**
 * M3-A03 任务查询 / M3-A06 云台当前任务恢复（DD 5、6.1、7.1）。
 * 纯查询、无副作用；失败投影严格有界（{@link FailureProjection}）。
 */
@Service
public class AssessmentReadService {

    private final AssessmentRepository assessmentRepository;
    private final AssessmentGimbalRepository gimbalRepository;
    private final AssessmentAccessRepository accessRepository;
    private final FailureProjection failureProjection;

    public AssessmentReadService(AssessmentRepository assessmentRepository,
                                 AssessmentGimbalRepository gimbalRepository,
                                 AssessmentAccessRepository accessRepository,
                                 FailureProjection failureProjection) {
        this.assessmentRepository = assessmentRepository;
        this.gimbalRepository = gimbalRepository;
        this.accessRepository = accessRepository;
        this.failureProjection = failureProjection;
    }

    public AssessmentTaskView getTask(UUID taskId, PrincipalContext principal) {
        AssessmentRepository.ViewRow row = assessmentRepository.findById(taskId)
                .orElseThrow(() -> notVisible());

        if (principal.principalType() == PrincipalType.GIMBAL) {
            if (!principal.gimbalUuid().equals(row.gimbalId())) {
                throw notVisible();
            }
            AssessmentGimbalRepository.Pointer pointer = gimbalRepository
                    .findById(principal.gimbalUuid())
                    .orElseThrow(AssessmentReadService::notVisible);
            if (!taskId.equals(pointer.currentAssessmentId())) {
                throw new ApiException(ErrorCode.TASK_REPLACED,
                        "assessment is no longer the gimbal current task");
            }
        } else {
            if (row.memberId() == null) {
                throw notVisible();
            }
            if (!accessRepository.hasActiveGrant(principal.accountUuid(), row.memberId())) {
                throw notVisible();
            }
        }

        List<String> requiredViews = failureProjection.requiredViews(row.status(),
                row.identityResult());
        Boolean retryable = failureProjection.retryable(row.failureCode());
        String failureCode = failureProjection.failureCode(row.failureCode());
        String reportId = "report_ready".equals(row.status()) && row.reportId() != null
                ? row.reportId().toString() : null;
        String planAvailability = accessRepository.planStatusByAssessmentId(taskId).orElse(null);
        return new AssessmentTaskView(
                row.id().toString(),
                row.status(),
                String.valueOf(row.currentPhotoVersion()),
                requiredViews,
                failureCode,
                retryable,
                reportId,
                planAvailability);
    }

    public GimbalCurrentAssessmentView currentAssessment(UUID gimbalId, PrincipalContext principal) {
        if (principal.principalType() != PrincipalType.GIMBAL
                || !gimbalId.equals(principal.gimbalUuid())) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "only the gimbal itself may query its current assessment");
        }
        AssessmentGimbalRepository.Pointer pointer = gimbalRepository.findById(gimbalId)
                .orElseThrow(AssessmentReadService::notVisible);
        String revision = String.valueOf(pointer.currentAssessmentRevision());
        if (pointer.currentAssessmentId() == null) {
            return new GimbalCurrentAssessmentView(null, revision);
        }
        AssessmentRepository.ViewRow row = assessmentRepository
                .findById(pointer.currentAssessmentId()).orElse(null);
        if (row == null) {
            return new GimbalCurrentAssessmentView(null, revision);
        }
        String reportId = "report_ready".equals(row.status()) && row.reportId() != null
                ? row.reportId().toString() : null;
        return new GimbalCurrentAssessmentView(
                new GimbalCurrentAssessmentView.CurrentAssessment(
                        row.id().toString(), row.status(),
                        String.valueOf(row.currentPhotoVersion()), reportId),
                revision);
    }

    private static ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, "assessment not visible");
    }
}

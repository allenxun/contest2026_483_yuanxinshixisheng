package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.assessments.AssessmentMultipartParser.ParsedA01;
import cn.yuanxin.mvp.web.assessments.AssessmentMultipartParser.ParsedA02;
import cn.yuanxin.mvp.web.assessments.dto.AssessmentTaskView;
import cn.yuanxin.mvp.web.assessments.dto.GimbalCurrentAssessmentView;
import cn.yuanxin.mvp.web.assessments.dto.SkinReportListItem;
import cn.yuanxin.mvp.web.assessments.dto.SkinReportView;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.ListData;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/**
 * M3 测肤任务与报告 HTTP 端点（M3-A01…A06；DD 5、7.1、8.1/8.2、10.1）。
 * Controller 只做 HTTP 映射/主体校验/信封；业务与事务在应用服务。
 */
@RestController
@Validated
@RequestMapping("/api/v1")
public class AssessmentController {

    private final AssessmentMultipartParser parser;
    private final AssessmentAcceptanceService acceptanceService;
    private final AssessmentReadService readService;
    private final SkinReportService skinReportService;
    private final EnvelopeSupport envelopes;

    public AssessmentController(AssessmentMultipartParser parser,
                                AssessmentAcceptanceService acceptanceService,
                                AssessmentReadService readService,
                                SkinReportService skinReportService,
                                EnvelopeSupport envelopes) {
        this.parser = parser;
        this.acceptanceService = acceptanceService;
        this.readService = readService;
        this.skinReportService = skinReportService;
        this.envelopes = envelopes;
    }

    @PostMapping("/skin-assessment-tasks")
    public ResponseEntity<SuccessEnvelope> create(
            @RequestHeader("Idempotency-Key") @Size(min = 1, max = 128) String idempotencyKey,
            PrincipalContext principal, HttpServletRequest request) {
        requireGimbal(principal);
        ParsedA01 parsed = parser.parseA01(request);
        AssessmentAcceptanceService.Accepted accepted =
                acceptanceService.acceptA01(principal, idempotencyKey, parsed);
        return ResponseEntity.status(accepted.replayed() ? 200 : 202)
                .body(envelopes.ok(request, accepted.data(), accepted.replayed()));
    }

    @PutMapping("/skin-assessment-tasks/{taskId}/photo-versions/{photoVersion}")
    public ResponseEntity<SuccessEnvelope> retake(
            @PathVariable UUID taskId,
            @PathVariable @Pattern(regexp = "^(0|[1-9][0-9]*)$",
                    message = "photoVersion must be a decimal bigint string") String photoVersion,
            @RequestHeader("Idempotency-Key") @Size(min = 1, max = 128) String idempotencyKey,
            PrincipalContext principal, HttpServletRequest request) {
        requireGimbal(principal);
        ParsedA02 parsed = parser.parseA02(request);
        AssessmentAcceptanceService.Accepted accepted =
                acceptanceService.acceptA02(principal, idempotencyKey, taskId, photoVersion, parsed);
        return ResponseEntity.status(accepted.replayed() ? 200 : 202)
                .body(envelopes.ok(request, accepted.data(), accepted.replayed()));
    }

    @GetMapping("/skin-assessment-tasks/{taskId}")
    public ResponseEntity<SuccessEnvelope> task(@PathVariable UUID taskId,
                                                PrincipalContext principal,
                                                HttpServletRequest request) {
        AssessmentTaskView view = readService.getTask(taskId, principal);
        return noStore(envelopes.ok(request, view));
    }

    @GetMapping("/members/{memberId}/skin-reports")
    public ResponseEntity<SuccessEnvelope> listReports(
            @PathVariable UUID memberId,
            @RequestParam(value = "limit", required = false) Integer limit,
            @RequestParam(value = "cursor", required = false) String cursor,
            PrincipalContext principal, HttpServletRequest request) {
        ListData<SkinReportListItem> data = skinReportService.listReports(
                memberId, limit, cursor, principal);
        return noStore(envelopes.ok(request, data));
    }

    @GetMapping("/skin-reports/{reportId}")
    public ResponseEntity<SuccessEnvelope> report(
            @PathVariable UUID reportId,
            @RequestParam(value = "view", required = false) String view,
            PrincipalContext principal, HttpServletRequest request) {
        SkinReportView data = skinReportService.getReport(reportId, view, principal);
        return noStore(envelopes.ok(request, data));
    }

    @GetMapping("/gimbals/{gimbalId}/current-assessment")
    public ResponseEntity<SuccessEnvelope> currentAssessment(@PathVariable UUID gimbalId,
                                                             PrincipalContext principal,
                                                             HttpServletRequest request) {
        GimbalCurrentAssessmentView data = readService.currentAssessment(gimbalId, principal);
        return ResponseEntity.ok().body(envelopes.ok(request, data));
    }

    private static void requireGimbal(PrincipalContext principal) {
        if (principal.principalType() != PrincipalType.GIMBAL) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "only a gimbal may submit skin assessment tasks");
        }
    }

    private static ResponseEntity<SuccessEnvelope> noStore(SuccessEnvelope body) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body);
    }
}

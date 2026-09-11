package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/**
 * M4 护理管理查询端点（A01/A02/A07/A08/A09）：薄控制器，逻辑在
 * {@link CareQueryService}。全部响应 {@code Cache-Control: no-store}，
 * 成功信封 {@code EnvelopeSupport.ok(request, data)}（GET 无 replayed）。
 */
@RestController
public class CareQueryController {

    private final CareQueryService careQueryService;
    private final EnvelopeSupport envelopes;

    public CareQueryController(CareQueryService careQueryService, EnvelopeSupport envelopes) {
        this.careQueryService = careQueryService;
        this.envelopes = envelopes;
    }

    /** M4-A01 列出本人方案与生成状态（APP）。 */
    @GetMapping("/api/v1/members/{memberId}/care-plans")
    public ResponseEntity<SuccessEnvelope> listMemberCarePlans(
            @PathVariable UUID memberId,
            @RequestParam(required = false) UUID reportId,
            @RequestParam(required = false) Integer limit,
            @RequestParam(required = false) String cursor,
            PrincipalContext principal, HttpServletRequest request) {
        return ok(request, careQueryService.listMemberCarePlans(principal, memberId, reportId,
                limit, cursor));
    }

    /** M4-A02 查询方案完整版（APP，view=full）。 */
    @GetMapping("/api/v1/care-plans/{planId}")
    public ResponseEntity<SuccessEnvelope> getCarePlan(
            @PathVariable UUID planId,
            @RequestParam(required = false) String view,
            PrincipalContext principal, HttpServletRequest request) {
        return ok(request, careQueryService.getCarePlan(principal, planId, view));
    }

    /** M4-A07 查询执行及对账状态（原控制端最小投影 / 授权 APP 完整摘要）。 */
    @GetMapping("/api/v1/care-executions/{executionId}")
    public ResponseEntity<SuccessEnvelope> getCareExecution(
            @PathVariable UUID executionId,
            @RequestParam(required = false) String recordsAfterSeq,
            @RequestParam(required = false) Integer limit,
            PrincipalContext principal, HttpServletRequest request) {
        return ok(request, careQueryService.getCareExecution(principal, executionId,
                recordsAfterSeq, limit));
    }

    /** M4-A08 查询方案累计进度（APP 或具备当前核验上下文的云台）。 */
    @GetMapping("/api/v1/care-plans/{planId}/progress")
    public ResponseEntity<SuccessEnvelope> getCarePlanProgress(
            @PathVariable UUID planId,
            @RequestParam(required = false) String executionId,
            @RequestParam(required = false) String verificationRevision,
            PrincipalContext principal, HttpServletRequest request) {
        return ok(request, careQueryService.getPlanProgress(principal, planId, executionId,
                verificationRevision));
    }

    /** M4-A09 查看本人护理执行历史（APP）。 */
    @GetMapping("/api/v1/members/{memberId}/care-executions")
    public ResponseEntity<SuccessEnvelope> listMemberCareExecutions(
            @PathVariable UUID memberId,
            @RequestParam(required = false) UUID planId,
            @RequestParam(required = false) String from,
            @RequestParam(required = false) String to,
            @RequestParam(required = false) Integer limit,
            @RequestParam(required = false) String cursor,
            PrincipalContext principal, HttpServletRequest request) {
        return ok(request, careQueryService.listMemberCareExecutions(principal, memberId, planId,
                from, to, limit, cursor));
    }

    private ResponseEntity<SuccessEnvelope> ok(HttpServletRequest request, Object data) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(envelopes.ok(request, data));
    }
}

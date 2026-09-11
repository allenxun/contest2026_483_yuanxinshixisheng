package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.ClosureRequestDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.SyncRequestDto;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/**
 * M4-A05 / M4-A06 JSON 写端点（薄控制器，逻辑在 {@link CareLedgerService}）。
 * 两者强制 {@code Idempotency-Key}（缺失 → 400 INVALID_INPUT），成功与重放
 * 均 200 且 {@code Cache-Control: no-store}；重放 {@code meta.replayed=true}。
 */
@RestController
public class CareLedgerController {

    private final CareLedgerService careLedgerService;
    private final EnvelopeSupport envelopes;

    public CareLedgerController(CareLedgerService careLedgerService, EnvelopeSupport envelopes) {
        this.careLedgerService = careLedgerService;
        this.envelopes = envelopes;
    }

    /** M4-A05 同步实际状态与有效完成记录（原控制端 APP 或云台）。 */
    @PostMapping("/api/v1/care-executions/{executionId}/observations")
    public ResponseEntity<SuccessEnvelope> syncObservation(
            @PathVariable UUID executionId,
            @RequestBody @Valid SyncRequestDto body,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            PrincipalContext principal, HttpServletRequest request) {
        requireIdempotencyKey(idempotencyKey);
        var outcome = careLedgerService.sync(principal, executionId, body, idempotencyKey);
        return respond(request, outcome.data(), outcome.replayed());
    }

    /** M4-A06 确认本地已停止并完成执行收尾（原控制端 APP 或云台）。 */
    @PostMapping("/api/v1/care-executions/{executionId}/closure-confirmations")
    public ResponseEntity<SuccessEnvelope> confirmClosure(
            @PathVariable UUID executionId,
            @RequestBody @Valid ClosureRequestDto body,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            PrincipalContext principal, HttpServletRequest request) {
        requireIdempotencyKey(idempotencyKey);
        var outcome = careLedgerService.close(principal, executionId, body, idempotencyKey);
        return respond(request, outcome.data(), outcome.replayed());
    }

    private static void requireIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "Idempotency-Key header is required");
        }
    }

    private ResponseEntity<SuccessEnvelope> respond(HttpServletRequest request, Object data,
                                                    boolean replayed) {
        if (replayed) {
            request.setAttribute(EnvelopeSupport.ATTR_REPLAYED, Boolean.TRUE);
        }
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(envelopes.ok(request, data, replayed));
    }
}

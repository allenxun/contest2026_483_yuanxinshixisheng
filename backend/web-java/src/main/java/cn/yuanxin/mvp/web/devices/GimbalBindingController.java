package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/**
 * M2-A06 绑定（PUT /api/v1/me/gimbal-bindings/{gimbalId}）、M2-A07 绑定状态
 * （GET /api/v1/gimbals/{gimbalId}/binding-status）、M2-A08 解绑
 * （DELETE /api/v1/me/gimbal-bindings/{gimbalId}）。
 *
 * <p>三者主体均仅 APP（云台 → 403 CALLER_NOT_ALLOWED）。A06/A08 必带
 * Idempotency-Key；A07 必带 X-Pairing-Proof 头；A08 可选
 * {@code If-Match: "binding-{revision}"}。成功解绑返回 204，无响应体。</p>
 */
@RestController
@RequestMapping("/api/v1")
public class GimbalBindingController {

    private final GimbalBindingService service;
    private final EnvelopeSupport envelopes;

    public GimbalBindingController(GimbalBindingService service, EnvelopeSupport envelopes) {
        this.service = service;
        this.envelopes = envelopes;
    }

    @PutMapping("/me/gimbal-bindings/{gimbalId}")
    public SuccessEnvelope bind(@PathVariable("gimbalId") UUID gimbalId,
                                @Valid @RequestBody DeviceDtos.BindingBody body,
                                @RequestHeader(value = "Idempotency-Key", required = false)
                                String idempotencyKey,
                                PrincipalContext principal, HttpServletRequest request) {
        GimbalBindingService.BindOutcome outcome =
                service.bind(principal, gimbalId, body, idempotencyKey);
        return envelopes.ok(request, outcome.view(), outcome.replayed());
    }

    @GetMapping("/gimbals/{gimbalId}/binding-status")
    public SuccessEnvelope bindingStatus(
            @PathVariable("gimbalId") UUID gimbalId,
            @RequestHeader(value = "X-Pairing-Proof", required = false) String pairingProof,
            PrincipalContext principal, HttpServletRequest request) {
        return envelopes.ok(request, service.bindingStatus(principal, gimbalId, pairingProof));
    }

    @DeleteMapping("/me/gimbal-bindings/{gimbalId}")
    public ResponseEntity<Void> unbind(
            @PathVariable("gimbalId") UUID gimbalId,
            @RequestHeader(value = "If-Match", required = false) String ifMatch,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            PrincipalContext principal) {
        service.unbind(principal, gimbalId, ifMatch, idempotencyKey);
        return ResponseEntity.noContent().build();
    }
}

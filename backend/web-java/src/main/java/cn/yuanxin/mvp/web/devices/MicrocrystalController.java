package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/**
 * M2-A04 微晶观察登记（POST /api/v1/microcrystal-observations）与
 * M2-A05 能力读取（GET /api/v1/microcrystals/{microcrystalId}/capabilities）。
 *
 * <p>两者主体均为 APP 或云台。A04 必带 Idempotency-Key；A05 的
 * X-Connection-Proof 可选，缺失时按"最近一次观察 observer_ref 是否与当前主体
 * 一致"推定，推不出 → 403，已被他人观察 → 404。GET 无副作用。</p>
 */
@RestController
@RequestMapping("/api/v1")
public class MicrocrystalController {

    private final MicrocrystalService service;
    private final EnvelopeSupport envelopes;

    public MicrocrystalController(MicrocrystalService service, EnvelopeSupport envelopes) {
        this.service = service;
        this.envelopes = envelopes;
    }

    @PostMapping("/microcrystal-observations")
    public SuccessEnvelope observe(
            @Valid @RequestBody DeviceDtos.MicrocrystalObservationBody body,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            PrincipalContext principal, HttpServletRequest request) {
        MicrocrystalService.ObservationOutcome outcome =
                service.report(principal, body, idempotencyKey);
        return envelopes.ok(request, outcome.ack(), outcome.replayed());
    }

    @GetMapping("/microcrystals/{microcrystalId}/capabilities")
    public SuccessEnvelope capabilities(
            @PathVariable("microcrystalId") UUID microcrystalId,
            @RequestHeader(value = "X-Connection-Proof", required = false) String connectionProof,
            PrincipalContext principal, HttpServletRequest request) {
        return envelopes.ok(request, service.capabilities(principal, microcrystalId, connectionProof));
    }
}

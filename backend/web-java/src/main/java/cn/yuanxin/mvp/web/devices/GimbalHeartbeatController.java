package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.UUID;

/**
 * M2-A02 云台心跳（POST /api/v1/gimbals/{gimbalId}/heartbeats）。
 *
 * <p>仅云台主体；APP → 403 CALLER_NOT_ALLOWED；他人云台/不存在 → 同一 404。
 * 不使用 Idempotency-Key（去重靠 epoch/seq）。含设备状态，响应统一
 * {@code Cache-Control: no-store}。响应 200 accepted 可为 false（旧序号仍确认收到）。</p>
 */
@RestController
@RequestMapping("/api/v1")
public class GimbalHeartbeatController {

    private final GimbalHeartbeatService service;
    private final EnvelopeSupport envelopes;

    public GimbalHeartbeatController(GimbalHeartbeatService service, EnvelopeSupport envelopes) {
        this.service = service;
        this.envelopes = envelopes;
    }

    @PostMapping("/gimbals/{gimbalId}/heartbeats")
    public ResponseEntity<SuccessEnvelope> heartbeat(@PathVariable("gimbalId") UUID gimbalId,
                                                     @Valid @RequestBody DeviceDtos.HeartbeatBody body,
                                                     PrincipalContext principal,
                                                     HttpServletRequest request) {
        GimbalHeartbeatService.Result result = service.report(principal, gimbalId, body);
        Instant now = Instant.now();
        Instant lastSeenAt = result.lastSeenAt() == null ? now : result.lastSeenAt();
        DeviceDtos.HeartbeatAck ack = new DeviceDtos.HeartbeatAck(result.accepted(),
                EnvelopeSupport.rfc3339(lastSeenAt), String.valueOf(result.statusRevision()),
                EnvelopeSupport.rfc3339(now));
        return ResponseEntity.ok()
                .header("Cache-Control", "no-store")
                .body(envelopes.ok(request, ack));
    }
}

package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/**
 * M2-A03 云台状态查询（GET /api/v1/gimbals/{gimbalId}/status）。
 *
 * <p>绑定账号或云台自身可读；其他账号/云台/不存在统一 404（不可区分）。
 * GET 无副作用（不写库、不递增 revision、不触发扫描）。</p>
 */
@RestController
@RequestMapping("/api/v1")
public class GimbalStatusController {

    private final GimbalStatusService service;
    private final EnvelopeSupport envelopes;

    public GimbalStatusController(GimbalStatusService service, EnvelopeSupport envelopes) {
        this.service = service;
        this.envelopes = envelopes;
    }

    @GetMapping("/gimbals/{gimbalId}/status")
    public SuccessEnvelope status(@PathVariable("gimbalId") UUID gimbalId,
                                  PrincipalContext principal, HttpServletRequest request) {
        return envelopes.ok(request, service.status(principal, gimbalId));
    }
}

package cn.yuanxin.mvp.web.notifications;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * M5-A01 {@code PUT /api/v1/me/notification-destinations/{installationId}}：
 * 已登录 APP 登记本安装实例的推送目标（DD M5-A01；lane-m5 第一部分）。
 *
 * <ul>
 *   <li>主体**仅 APP**（云台 token → 403 CALLER_NOT_ALLOWED）；身份只来自 token。</li>
 *   <li>路径 {@code installationId} 必须**等于** {@code principal.installationId()}，
 *       否则 403 CALLER_NOT_ALLOWED——不能仅凭 installationId 抢占或替他人登记；
 *       路径空白/超 128 → 400 INVALID_INPUT。</li>
 *   <li>请求体 platform 仅 android；registration 非空且 schema_version 为整数；
 *       {@code Idempotency-Key} 必填。</li>
 *   <li>响应只含 destinationId/destinationRevision/status，永不回传推送 token；
 *       header {@code Cache-Control: no-store}（X-Request-Id 由 RequestIdFilter 统一加）。</li>
 *   <li>本接口只登记目标，**不发送任何消息**。</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/v1/me/notification-destinations")
public class NotificationDestinationController {

    private final NotificationDestinationService service;
    private final EnvelopeSupport envelopes;

    public NotificationDestinationController(NotificationDestinationService service,
                                             EnvelopeSupport envelopes) {
        this.service = service;
        this.envelopes = envelopes;
    }

    @PutMapping("/{installationId}")
    public ResponseEntity<SuccessEnvelope> register(
            @PathVariable("installationId") String installationId,
            @Valid @RequestBody NotificationDestinationDtos.Request body,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            PrincipalContext principal,
            HttpServletRequest request) {
        requireApp(principal);
        requireMatchingInstallation(installationId, principal);
        requireIdempotencyKey(idempotencyKey);
        requireAndroid(body.platform());

        NotificationDestinationService.RegisterResult result =
                service.register(principal, installationId, body, idempotencyKey);
        NotificationDestinationDtos.View view = new NotificationDestinationDtos.View(
                result.destinationId(), result.destinationRevision(), result.status());
        return ResponseEntity.ok()
                .header("Cache-Control", "no-store")
                .body(envelopes.ok(request, view, result.replayed()));
    }

    private static void requireApp(PrincipalContext principal) {
        if (principal.principalType() != PrincipalType.APP) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "this endpoint is only available to app account sessions");
        }
    }

    private static void requireMatchingInstallation(String installationId, PrincipalContext principal) {
        if (installationId == null || installationId.isBlank() || installationId.length() > 128) {
            throw new ApiException(ErrorCode.INVALID_INPUT,
                    "installationId must be 1-128 characters");
        }
        if (!installationId.equals(principal.installationId())) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "installationId does not belong to the authenticated session");
        }
    }

    private static void requireIdempotencyKey(String key) {
        if (key == null || key.isBlank() || key.length() > 128) {
            throw new ApiException(ErrorCode.INVALID_INPUT,
                    "Idempotency-Key header is required (1-128 characters)");
        }
    }

    private static void requireAndroid(String platform) {
        if (!"android".equals(platform)) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "platform must be android");
        }
    }
}

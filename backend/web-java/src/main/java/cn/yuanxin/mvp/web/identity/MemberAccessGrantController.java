package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.media.MediaIntakeService;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.ListData;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;

import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * M1 成员身份与查看授权控制器（B 包 L2）。
 *
 * <ul>
 *   <li>{@code POST /api/v1/member-access-grants}（M1-A01）：APP multipart
 *       face 授权；可靠匹配 → 201 新 active 关系 / 200 已存在或 T13 重放；
 *       无可靠匹配 → 403 FACE_NOT_VERIFIED（不返回候选/不泄露成员是否存在）；
 *       已撤销关系的旧 T13 重放 → 403 GRANT_REVOKED，绝不复活。</li>
 *   <li>{@code GET /api/v1/me/member-access-grants}（M1-A02）：APP，仅当前
 *       账号 active 关系，keyset 分页（created_at DESC, id DESC）；GET 无副作用。</li>
 *   <li>{@code DELETE /api/v1/me/member-access-grants/{grantId}}（M1-A03）：
 *       APP 且 grant 所属账号；204 无响应体；不存在/他人 → 同一 404
 *       RESOURCE_NOT_VISIBLE；重复撤销幂等 204。</li>
 * </ul>
 *
 * <p>身份只来自 token；主体类型不符（云台）→ 403 CALLER_NOT_ALLOWED。
 * 响应 JSON camelCase、时间 RFC3339 UTC；错误经 GlobalExceptionHandler 统一
 * 成信封，控制器不自拼错误体。</p>
 */
@RestController
public class MemberAccessGrantController {

    private static final Set<String> ALLOWED_PARTS = Set.of("metadata", "face");

    private final MemberAccessGrantService service;
    private final EnvelopeSupport envelopes;
    private final ObjectMapper objectMapper;
    private final AppProperties appProperties;

    public MemberAccessGrantController(MemberAccessGrantService service, EnvelopeSupport envelopes,
                                       ObjectMapper objectMapper, AppProperties appProperties) {
        this.service = service;
        this.envelopes = envelopes;
        this.objectMapper = objectMapper;
        this.appProperties = appProperties;
    }

    // ---------- request / response shapes ----------

    /** M1A01Metadata：additionalProperties:false（未知字段如 memberId → 400）。 */
    public record M1A01Metadata(Capture capture, String consentEvidenceRef) {
    }

    /** Capture：additionalProperties:false；purpose 仅 grant 在本端点合法。 */
    public record Capture(String captureId, String capturedAt, String clientContinuityId,
                          String purpose, String captureProofRef) {
    }

    /** MemberAccessGrantResult：契约 required=[grantId,memberId,status,grantedAt]，不额外加字段。 */
    public record MemberAccessGrantResult(String grantId, String memberId, String status,
                                          String grantedAt) {
    }

    // ---------- M1-A01 ----------

    @PostMapping(path = "/api/v1/member-access-grants",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<SuccessEnvelope> create(MultipartHttpServletRequest multipart,
                                                  @RequestHeader(value = "Idempotency-Key",
                                                          required = false) String idempotencyKey,
                                                  PrincipalContext principal,
                                                  HttpServletRequest request) throws IOException {
        requireApp(principal);
        requireIdempotencyKey(idempotencyKey);

        Map<String, MultipartFile> files = multipart.getFileMap();
        if (!files.keySet().equals(ALLOWED_PARTS)
                || !multipart.getParameterMap().isEmpty()) {
            throw invalidInput("multipart parts must be exactly metadata and face");
        }
        byte[] metadataBytes = files.get("metadata").getBytes();
        byte[] faceBytes = files.get("face").getBytes();
        if (faceBytes.length == 0 || faceBytes.length > appProperties.limits().maxImageBytes()) {
            if (faceBytes.length == 0) {
                throw new ApiException(ErrorCode.UNSUPPORTED_IMAGE, "face image is empty");
            }
            throw new ApiException(ErrorCode.UPLOAD_TOO_LARGE, "face image exceeds configured limit");
        }
        // 实际格式嗅探（不信任客户端 MIME），在任何写入之前。
        MediaIntakeService.sniffImageContentType(faceBytes);
        MemberAccessGrantService.CreateMetadata metadata = parseMetadata(metadataBytes);

        MemberAccessGrantService.CreateOutcome outcome =
                service.createGrant(principal, idempotencyKey, metadata, faceBytes);
        MemberAccessGrantResult data = new MemberAccessGrantResult(outcome.grantId().toString(),
                outcome.memberId().toString(), "active",
                EnvelopeSupport.rfc3339(outcome.grantedAt()));
        HttpStatus status = outcome.created() ? HttpStatus.CREATED : HttpStatus.OK;
        return ResponseEntity.status(status)
                .header("Cache-Control", "no-store")
                .body(envelopes.ok(request, data, outcome.replayed()));
    }

    // ---------- M1-A02 ----------

    @GetMapping("/api/v1/me/member-access-grants")
    public ResponseEntity<SuccessEnvelope> list(
            @RequestParam(value = "limit", required = false) Integer limit,
            @RequestParam(value = "cursor", required = false) String cursor,
            PrincipalContext principal, HttpServletRequest request) {
        ListData<MemberAccessGrantService.MemberAccessGrantListItem> data =
                service.listGrants(principal, limit, cursor);
        return ResponseEntity.ok()
                .header("Cache-Control", "no-store")
                .body(envelopes.ok(request, data));
    }

    // ---------- M1-A03 ----------

    @DeleteMapping("/api/v1/me/member-access-grants/{grantId}")
    public ResponseEntity<Void> revoke(@PathVariable("grantId") UUID grantId,
                                       @RequestHeader(value = "Idempotency-Key",
                                               required = false) String idempotencyKey,
                                       PrincipalContext principal) {
        requireApp(principal);
        requireIdempotencyKey(idempotencyKey);
        service.revokeGrant(principal, grantId, idempotencyKey);
        return ResponseEntity.noContent().build();
    }

    // ---------- validation helpers ----------

    private MemberAccessGrantService.CreateMetadata parseMetadata(byte[] raw) {
        M1A01Metadata parsed;
        try {
            parsed = objectMapper.readValue(raw, M1A01Metadata.class);
        } catch (IOException e) {
            throw invalidInput("metadata is not a valid strict JSON object");
        }
        Capture capture = parsed.capture();
        if (capture == null) {
            throw invalidInput("metadata.capture is required");
        }
        requireText(capture.captureId(), "captureId");
        requireText(capture.clientContinuityId(), "clientContinuityId");
        requireText(parsed.consentEvidenceRef(), "consentEvidenceRef");
        validateTimestamp(capture.capturedAt());
        if (!"grant".equals(capture.purpose())) {
            throw invalidInput("capture.purpose must be grant for this endpoint");
        }
        return new MemberAccessGrantService.CreateMetadata(capture.captureId(), capture.capturedAt(),
                capture.clientContinuityId(), capture.purpose(), capture.captureProofRef(),
                parsed.consentEvidenceRef());
    }

    private static void requireApp(PrincipalContext principal) {
        if (principal.principalType() != cn.yuanxin.mvp.web.auth.PrincipalType.APP) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "this endpoint is only available to app account sessions");
        }
    }

    private static void requireIdempotencyKey(String key) {
        if (key == null || key.isBlank() || key.length() > 128) {
            throw invalidInput("Idempotency-Key header is required (1-128 characters)");
        }
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank() || value.length() > 128) {
            throw invalidInput(field + " must be 1-128 characters");
        }
    }

    private static void validateTimestamp(String value) {
        if (value == null || value.isBlank()) {
            throw invalidInput("capturedAt is required");
        }
        try {
            OffsetDateTime.parse(value);
        } catch (RuntimeException e) {
            throw invalidInput("capturedAt must be an RFC3339 timestamp");
        }
    }

    private static ApiException invalidInput(String field) {
        return new ApiException(ErrorCode.INVALID_INPUT, field,
                Map.of("fields", java.util.List.of(Map.of("field", field, "reason", "invalid"))));
    }
}

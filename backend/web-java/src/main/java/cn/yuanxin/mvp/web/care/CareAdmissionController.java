package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.M4A03Metadata;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.M4A04Metadata;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.UUID;

/**
 * M4-A03 / M4-A04 multipart 写端点（薄控制器，逻辑在
 * {@link CareAdmissionService}）。
 *
 * <p>两者都强制 {@code Idempotency-Key}（缺失 → 400 INVALID_INPUT）。
 * 全部响应 {@code Cache-Control: no-store}；A03 新建 201、重放 200，
 * A04 成功/重放均 200；重放 {@code meta.replayed=true} 且
 * {@code verification.replayed=true}。</p>
 */
@RestController
public class CareAdmissionController {

    private final CareAdmissionService careAdmissionService;
    private final EnvelopeSupport envelopes;

    public CareAdmissionController(CareAdmissionService careAdmissionService,
                                   EnvelopeSupport envelopes) {
        this.careAdmissionService = careAdmissionService;
        this.envelopes = envelopes;
    }

    /** M4-A03 人脸核验、取得方案并登记新执行（APP 或云台）。 */
    @PostMapping(value = "/api/v1/care-executions",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<SuccessEnvelope> createCareExecution(
            @RequestPart(value = "metadata", required = false) @Valid M4A03Metadata metadata,
            @RequestPart(value = "face", required = false) MultipartFile face,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            PrincipalContext principal, HttpServletRequest request) throws IOException {
        requireIdempotencyKey(idempotencyKey);
        requireMultipartParts(metadata, face);
        var outcome = careAdmissionService.admit(principal, metadata, face.getBytes(),
                idempotencyKey);
        if (outcome.replayed()) {
            request.setAttribute(EnvelopeSupport.ATTR_REPLAYED, Boolean.TRUE);
        }
        return respond(request, outcome.data(), outcome.replayed() ? 200 : 201);
    }

    /** M4-A04 使用者连续性失效后重新核验恢复条件（原控制端 APP 或云台）。 */
    @PostMapping(value = "/api/v1/care-executions/{executionId}/revalidations",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<SuccessEnvelope> revalidateCareExecution(
            @PathVariable UUID executionId,
            @RequestPart(value = "metadata", required = false) @Valid M4A04Metadata metadata,
            @RequestPart(value = "face", required = false) MultipartFile face,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            PrincipalContext principal, HttpServletRequest request) throws IOException {
        requireIdempotencyKey(idempotencyKey);
        requireMultipartParts(metadata, face);
        var outcome = careAdmissionService.revalidate(principal, executionId, metadata,
                face.getBytes(), idempotencyKey);
        if (outcome.replayed()) {
            request.setAttribute(EnvelopeSupport.ATTR_REPLAYED, Boolean.TRUE);
        }
        return respond(request, outcome.data(), 200);
    }

    private static void requireMultipartParts(Object metadata, MultipartFile face) {
        if (metadata == null) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "metadata part is required");
        }
        if (face == null) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "face part is required");
        }
    }

    private static void requireIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "Idempotency-Key header is required");
        }
    }

    private ResponseEntity<SuccessEnvelope> respond(HttpServletRequest request, Object data,
                                                    int status) {
        return ResponseEntity.status(status)
                .cacheControl(CacheControl.noStore())
                .body(envelopes.ok(request, data,
                        Boolean.TRUE.equals(request.getAttribute(EnvelopeSupport.ATTR_REPLAYED))));
    }
}

package cn.yuanxin.mvp.web.care;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.UUID;

/**
 * M4-A03 / M4-A04 multipart {@code metadata} part 与成功响应 DTO
 * （逐字段对齐 contracts/openapi/openapi.yaml components.schemas）。
 *
 * <p>校验分工：Bean Validation 只表达契约中的必填/长度/字符集约束；
 * 角色化二选一、purpose 取值、capturedAt 可解析性等由
 * {@link CareAdmissionService} 在 T13 begin 之前显式校验（400 INVALID_INPUT）。</p>
 */
public final class CareAdmissionDtos {

    /** 契约 BigintString pattern。 */
    public static final String BIGINT_PATTERN = "^(0|[1-9][0-9]*)$";

    private CareAdmissionDtos() {
    }

    /** components.schemas.Capture（additionalProperties:false）。 */
    public record CaptureDto(
            @NotBlank @Size(max = 128) String captureId,
            @NotBlank String capturedAt,
            @NotBlank @Size(max = 128) String clientContinuityId,
            @NotBlank String purpose,
            String captureProofRef) {
    }

    /** components.schemas.M4A03Metadata（additionalProperties:false）。 */
    public record M4A03Metadata(
            @NotNull UUID microcrystalId,
            @NotBlank String connectionProof,
            @NotNull @Valid CaptureDto capture,
            @NotBlank @Size(max = 128) String consentEvidenceRef,
            UUID planId,
            UUID currentTaskId,
            @Pattern(regexp = BIGINT_PATTERN, message = "currentAssessmentRevision must be a bigint string")
            String currentAssessmentRevision) {
    }

    /** components.schemas.M4A04Metadata（additionalProperties:false）。 */
    public record M4A04Metadata(
            @NotBlank @Pattern(regexp = BIGINT_PATTERN,
                    message = "expectedVerificationRevision must be a bigint string")
            String expectedVerificationRevision,
            @NotNull @Valid CaptureDto capture,
            @NotBlank @Size(max = 128) String consentEvidenceRef,
            JsonNode reportedMicrocrystalState) {
    }

    /**
     * components.schemas.Verification（additionalProperties:true）：
     * required=[verificationRevision,captureId,clientContinuityId,verifiedAt,
     * applicablePurpose,replayed]。
     */
    public record VerificationDto(String verificationRevision, String captureId,
                                  String clientContinuityId, String verifiedAt, String validUntil,
                                  String applicablePurpose, Boolean replayed) {
    }

    /** components.schemas.CareExecutionAdmission（additionalProperties:false）。 */
    public record CareExecutionAdmission(String executionId, String status,
                                         CareProjections.ControllerRef controller, String memberId,
                                         String planId, Object planExecution,
                                         CareProjections.Progress progress,
                                         VerificationDto verification, String recordStreamEpoch) {
    }

    /** components.schemas.CareExecutionRevalidation（additionalProperties:false）。 */
    public record CareExecutionRevalidation(String executionId, String status, String planId,
                                            Object planExecution, CareProjections.Progress progress,
                                            VerificationDto verification) {
    }
}

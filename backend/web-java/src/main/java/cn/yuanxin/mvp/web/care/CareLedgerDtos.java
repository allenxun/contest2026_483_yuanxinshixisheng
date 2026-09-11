package cn.yuanxin.mvp.web.care;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.List;

/**
 * M4-A05 / M4-A06 请求与成功响应 DTO（逐字段对齐
 * contracts/openapi/openapi.yaml components.schemas）。JSON 请求体，
 * {@code additionalProperties:false} 由全局 Jackson fail-on-unknown 保证。
 */
public final class CareLedgerDtos {

    private CareLedgerDtos() {
    }

    /** components.schemas.ExecutionObservation。state 枚举在服务层校验（400）。 */
    public record ExecutionObservationDto(
            @NotBlank @Size(max = 128) String epoch,
            @NotBlank @Pattern(regexp = CareAdmissionDtos.BIGINT_PATTERN,
                    message = "seq must be a bigint string") String seq,
            @NotBlank String state,
            @NotBlank String occurredAt,
            @Pattern(regexp = CareAdmissionDtos.BIGINT_PATTERN,
                    message = "verificationRevision must be a bigint string") String verificationRevision,
            Boolean continuityValid) {
    }

    /** components.schemas.ExecutionRecord。 */
    public record ExecutionRecordDto(
            @NotBlank @Size(max = 128) String recordId,
            @NotBlank @Size(max = 128) String sourceEpoch,
            @NotBlank @Pattern(regexp = CareAdmissionDtos.BIGINT_PATTERN,
                    message = "sourceSeq must be a bigint string") String sourceSeq,
            @NotBlank @Pattern(regexp = CareAdmissionDtos.BIGINT_PATTERN,
                    message = "countDelta must be a bigint string") String countDelta,
            @NotBlank String occurredAt) {
    }

    /** components.schemas.ExecutionObservationSyncRequest（records maxItems=200）。 */
    public record SyncRequestDto(
            @Valid ExecutionObservationDto observation,
            @NotNull @Size(max = 200) List<@Valid ExecutionRecordDto> records) {
    }

    /** components.schemas.AcknowledgedRecord。 */
    public record AcknowledgedRecordDto(String recordId, String disposition, String rejectReason) {
    }

    /** components.schemas.ExecutionObservationAck。 */
    public record ObservationAckDto(List<AcknowledgedRecordDto> acknowledgedRecords,
                                    String executionStatus, String acceptedCount,
                                    CareProjections.Progress progress) {
    }

    /** components.schemas.ExecutionClosureRequest。 */
    public record ClosureRequestDto(
            @NotBlank @Pattern(regexp = CareAdmissionDtos.BIGINT_PATTERN,
                    message = "stopObservationSeq must be a bigint string") String stopObservationSeq,
            @NotBlank @Size(max = 128) String reason,
            @NotBlank @Size(max = 128) String recordStreamEpoch,
            @NotBlank @Pattern(regexp = CareAdmissionDtos.BIGINT_PATTERN,
                    message = "finalRecordSeq must be a bigint string") String finalRecordSeq,
            @NotBlank @Pattern(regexp = CareAdmissionDtos.BIGINT_PATTERN,
                    message = "finalCount must be a bigint string") String finalCount) {
    }

    /** components.schemas.MissingRange。 */
    public record MissingRangeDto(String from, String to) {
    }

    /** components.schemas.ExecutionClosureResult。 */
    public record ClosureResultDto(Boolean closed, String closedAt, Boolean occupancyReleased) {
    }
}

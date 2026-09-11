package cn.yuanxin.mvp.web.devices;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * M2 设备端点请求/响应 DTO（契约 openapi L2146-2270）。
 *
 * <p>请求记录带 Bean Validation（缺字段/类型错/未知字段 → 400 INVALID_INPUT，
 * 全局 {@code fail-on-unknown-properties=true}）。响应记录字段名严格匹配契约，
 * bigint（revision/seq）一律十进制字符串，时间为 RFC3339 UTC 字符串。</p>
 */
public final class DeviceDtos {

    private static final String BIGINT = "^(0|[1-9][0-9]*)$";

    private DeviceDtos() {
    }

    // ---------------- M2-A02 ----------------

    public record HeartbeatBody(
            @NotBlank @Size(min = 1, max = 128) String observationEpoch,
            @NotBlank @Pattern(regexp = BIGINT,
                    message = "observationSeq must be an unsigned decimal bigint string")
            String observationSeq,
            @NotNull Instant observedAt,
            @NotNull PowerState powerState,
            String taskId,
            String executionId,
            List<Map<String, Object>> incidents) {
    }

    public record HeartbeatAck(boolean accepted, String lastSeenAt, String statusRevision,
                               String serverTime) {
    }

    // ---------------- M2-A03 ----------------

    public record IncidentView(String incidentId, String code, String severity,
                               String openedAt, String lastReportedAt) {
    }

    public record StatusView(String connectionStatus, String powerState, String lastSeenAt,
                             @JsonProperty("isStale") boolean isStale, String statusRevision,
                             List<IncidentView> incidents) {
    }

    // ---------------- M2-A04 / A05 ----------------

    public record MicrocrystalObservationBody(
            @NotBlank @Size(min = 1, max = 128) String microcrystalSerial,
            @NotBlank @Size(max = 8192) String connectionProof,
            @NotNull Map<String, Object> capabilities,
            @NotBlank @Size(min = 1, max = 128) String observationEpoch,
            @NotBlank @Pattern(regexp = BIGINT,
                    message = "observationSeq must be an unsigned decimal bigint string")
            String observationSeq,
            @NotNull Instant observedAt,
            @NotNull Map<String, Object> state) {
    }

    public record MicrocrystalObservationAck(String microcrystalId, boolean accepted,
                                             String capabilityRevision, String receivedAt) {
    }

    public record CapabilitiesView(Map<String, Object> capabilities, String capabilityRevision,
                                   String observedAt, String receivedAt,
                                   @JsonProperty("isStale") boolean isStale) {
    }

    // ---------------- M2-A06 / A07 / A08 ----------------

    public record BindingBody(
            @NotBlank @Pattern(regexp = BIGINT,
                    message = "expectedBindingRevision must be an unsigned decimal bigint string")
            String expectedBindingRevision,
            @NotBlank @Size(max = 8192) String pairingProof) {
    }

    public record BindingResultView(String bindingStatus, String gimbalId,
                                    String bindingRevision, String boundAt) {
    }

    public record BindingStatusView(String bindingStatus, String bindingRevision) {
    }
}

package cn.yuanxin.mvp.web.notifications;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.Map;

/**
 * M5-A01 请求/响应形状（contracts/openapi NotificationDestinationRequest /
 * NotificationDestinationView）。
 *
 * <p>请求 {@code additionalProperties:false}：全局
 * {@code spring.jackson.deserialization.fail-on-unknown-properties=true}
 * 会把未知字段（如伪造的 accountId/installationId）转成 400 INVALID_INPUT；
 * 身份只来自 token。</p>
 *
 * <p>响应只含 destinationId/destinationRevision/status——绝不回传完整推送
 * token / registration（契约响应体没有该字段）。destinationRevision 是
 * bigint，出 JSON 用十进制字符串（契约 BigintString）。</p>
 */
public final class NotificationDestinationDtos {

    private NotificationDestinationDtos() {
    }

    /** M5-A01 请求体；platform 用 String 以便对非 android 值给出明确 400。 */
    public record Request(
            @NotBlank @Size(max = 64) String provider,
            @NotBlank @Size(max = 32) String platform,
            @NotNull Map<String, Object> registration,
            @NotBlank @Pattern(regexp = "^(0|[1-9][0-9]*)$",
                    message = "expectedDestinationRevision must be an unsigned decimal bigint string")
            String expectedDestinationRevision) {
    }

    /** M5-A01 响应体：恰好三个字段。 */
    public record View(String destinationId, String destinationRevision, String status) {
    }
}

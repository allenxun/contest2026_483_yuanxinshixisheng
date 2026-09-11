package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.care.CareExecutionRepository.CareExecutionRow;
import cn.yuanxin.mvp.web.care.CarePlanRepository.CarePlanRow;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;

/**
 * M4 查询投影构造：DB 行 → 契约 DTO 的显式映射（绝不直接序列化 DB 行）。
 *
 * <p>JSONB 列由仓储以 {@code ::text} 取出，此处 Jackson readTree；空占位
 * {@code '{}'} 按各字段规则映射 null；{@link ExecutionObservation} 内部
 * snake_case 键映射 camelCase，缺少必填成员或不可解析时整体省略（null）。</p>
 */
@Component
public class CareProjections {

    private static final String EMPTY_OBJECT = "{}";

    private final ObjectMapper objectMapper;

    public CareProjections(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    // ---------- 契约 DTO ----------

    public record Progress(String targetCount, String completedCount, String remainingCount,
                           Boolean isCompleted, String progressRevision, String completedAt) {
    }

    public record ProgressWithSync(String targetCount, String completedCount, String remainingCount,
                                   Boolean isCompleted, String progressRevision, String completedAt,
                                   String lastSyncedAt) {
    }

    public record ExecutionObservation(String epoch, String seq, String state, String occurredAt,
                                       String verificationRevision, Boolean continuityValid) {
    }

    public record ControllerRef(String controllerType, String installationId, String gimbalId) {
    }

    public record RecordWatermark(String epoch, String maxSourceSeq, String acceptedCount) {
    }

    public record CarePlanListItem(String planId, String generationStatus, Object planSummary,
                                   Progress progress) {
    }

    public record CarePlanFullView(String planId, String generationStatus, Object plan,
                                   Progress progress, String waitingReason) {
    }

    public record CareExecutionListItem(String executionId, String status, String createdAt,
                                        String closedAt, String acceptedCount,
                                        Object planSnapshotSummary) {
    }

    public record CareExecutionView(String executionId, String status, ControllerRef controller,
                                    String memberId, String planId, String microcrystalId,
                                    String acceptedCount, ExecutionObservation latestObservation,
                                    RecordWatermark recordWatermark,
                                    List<String> acknowledgedRecordIds, String closedAt,
                                    Progress progress) {
    }

    // ---------- 投影构造 ----------

    /** Progress（仅基于 T06 已提交值；剩余 = max(N-K,0)，完成 = K>=N）。 */
    public Progress progressFor(CarePlanRow row) {
        Long target = row.targetCount();
        long completed = row.completedCount();
        return new Progress(
                CareBigints.out(target),
                CareBigints.out(completed),
                target == null ? "0" : CareBigints.out(Math.max(target - completed, 0)),
                target == null ? null : completed >= target,
                CareBigints.out(row.progressRevision()),
                rfc3339(row.completedAt()));
    }

    /** M4-A08 ProgressWithSync：Progress + lastSyncedAt（progress_revision>0 时 updated_at）。 */
    public ProgressWithSync progressWithSync(CarePlanRow row) {
        Progress p = progressFor(row);
        String lastSyncedAt = row.progressRevision() > 0 ? rfc3339(row.updatedAt()) : null;
        return new ProgressWithSync(p.targetCount(), p.completedCount(), p.remainingCount(),
                p.isCompleted(), p.progressRevision(), p.completedAt(), lastSyncedAt);
    }

    /** T07.latest_observation JSONB → ExecutionObservation（内部 snake_case → camelCase）。 */
    public ExecutionObservation executionObservation(String raw) {
        JsonNode node = readObject(raw);
        if (node == null) {
            return null;
        }
        String epoch = textOrNull(node, "epoch");
        String seq = bigintOrNull(node, "seq");
        String state = textOrNull(node, "state");
        String occurredAt = textOrNull(node, "occurred_at", "occurredAt");
        if (epoch == null || seq == null || state == null || occurredAt == null) {
            return null;
        }
        String verificationRevision = bigintOrNull(node, "verification_revision", "verificationRevision");
        Boolean continuityValid = booleanOrNull(node, "continuity_valid", "continuityValid");
        return new ExecutionObservation(epoch, seq, state, occurredAt,
                verificationRevision, continuityValid);
    }

    /** 固定控制端投影：db 'app'→app_account+installationId；'gimbal'→gimbal+gimbalId。 */
    public ControllerRef controllerRef(CareExecutionRow row) {
        return switch (row.controllerType()) {
            case "app" -> new ControllerRef("app_account", row.controllerInstallationId(), null);
            case "gimbal" -> new ControllerRef("gimbal", null,
                    row.controllerGimbalId() == null ? null : row.controllerGimbalId().toString());
            default -> null;
        };
    }

    /** 记录水位：epoch + 该流已接受最大序号 + 已接受总次数。 */
    public RecordWatermark recordWatermark(CareExecutionRow row, long maxSourceSeq) {
        return new RecordWatermark(row.observationEpoch(),
                CareBigints.out(maxSourceSeq), CareBigints.out(row.acceptedCount()));
    }

    /** T06.plan_summary：'{}'/空/不可解析 → null，否则原对象。 */
    public Object planSummaryOrNull(String raw) {
        return jsonObjectOrNull(raw);
    }

    /** T06.plan_payload：ready 方案正文整体透传（对象）。 */
    public Object planPayloadOrNull(String raw) {
        JsonNode node = readObject(raw);
        return node == null || node.size() == 0 ? null : node;
    }

    /** T07.plan_snapshot.summary：无该键/'{}'/非对象 → null，否则 summary 对象。 */
    public Object planSnapshotSummaryOrNull(String raw) {
        JsonNode snapshot = readObject(raw);
        if (snapshot == null) {
            return null;
        }
        JsonNode summary = snapshot.path("summary");
        if (!summary.isObject() || summary.size() == 0) {
            return null;
        }
        return summary;
    }

    // ---------- helpers ----------

    private static String rfc3339(Instant instant) {
        return instant == null ? null : EnvelopeSupport.rfc3339(instant);
    }

    private JsonNode readObject(String raw) {
        if (raw == null || raw.isBlank() || EMPTY_OBJECT.equals(raw.trim())) {
            return null;
        }
        try {
            JsonNode node = objectMapper.readTree(raw);
            return node != null && node.isObject() && node.size() > 0 ? node : null;
        } catch (Exception parseFailure) {
            return null;
        }
    }

    /** 取字符串成员（按给定键序回退），空/缺失 → null。 */
    private static String textOrNull(JsonNode node, String... keys) {
        for (String key : keys) {
            JsonNode v = node.get(key);
            if (v != null && v.isTextual() && !v.asText().isBlank()) {
                return v.asText();
            }
        }
        return null;
    }

    /** 取 bigint 成员：textual 按契约 pattern 解析为十进制串，numeric 直接用。 */
    private static String bigintOrNull(JsonNode node, String... keys) {
        for (String key : keys) {
            JsonNode v = node.get(key);
            if (v == null || v.isNull()) {
                continue;
            }
            if (v.isTextual()) {
                try {
                    return CareBigints.out(CareBigints.parse(v.asText(), key));
                } catch (RuntimeException invalid) {
                    return null;
                }
            }
            if (v.isIntegralNumber()) {
                return CareBigints.out(v.asLong());
            }
        }
        return null;
    }

    private static Boolean booleanOrNull(JsonNode node, String... keys) {
        for (String key : keys) {
            JsonNode v = node.get(key);
            if (v == null || v.isNull()) {
                continue;
            }
            if (v.isBoolean()) {
                return v.booleanValue();
            }
        }
        return null;
    }

    private JsonNode jsonObjectOrNull(String raw) {
        return readObject(raw);
    }
}

package cn.yuanxin.mvp.web.care;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * T06 方案 JSONB 的<b>显式字段级白名单投影</b>（C 侧保守提案）。
 *
 * <p>背景：契约中 Plan.execution/plan_summary 为 {@code additionalProperties:true}
 * 的“结构未冻结”对象；整体透传会把供应商原始响应/提示词等敏感键泄露给客户端。
 * 因此 C 侧只放行已知的语义字段，未知键与类型不符值一律丢弃（仅以 WARN 记录
 * 键名，绝不记录内容），过滤后为空对象则投影为 {@code null}。</p>
 *
 * <p><b>白名单为 C 侧保守提案，待总协调/D 契约确认后冻结</b>；协议未冻结字段
 * 保守省略，不发明任何设备参数。schema_version 属内部版本标记，不在任何白名单中，
 * 绝不外发。</p>
 */
@Component
public class CarePlanProjection {

    private static final Logger log = LoggerFactory.getLogger(CarePlanProjection.class);

    private enum FieldType {
        STRING, ARRAY, OBJECT
    }

    /** A02 Plan.full 白名单。 */
    private static final Map<String, FieldType> FULL = whitelist(
            "title", FieldType.STRING,
            "description", FieldType.STRING,
            "steps", FieldType.ARRAY,
            "regions", FieldType.ARRAY,
            "parameters", FieldType.OBJECT);

    /** A03/A04 Plan.execution（快照 execution_params）白名单。 */
    private static final Map<String, FieldType> EXECUTION = whitelist(
            "steps", FieldType.ARRAY,
            "regions", FieldType.ARRAY,
            "parameters", FieldType.OBJECT);

    /** A01/A03 快照 summary/A09 快照摘要白名单。 */
    private static final Map<String, FieldType> SUMMARY = whitelist(
            "title", FieldType.STRING,
            "description", FieldType.STRING,
            "source_report_id", FieldType.STRING,
            "source_report_ready_at", FieldType.STRING);

    private final ObjectMapper objectMapper;

    public CarePlanProjection(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /** A02：plan_payload → Plan.full 投影（对象或 null）。 */
    public Object full(String rawPlanPayload) {
        return filter(rawPlanPayload, FULL);
    }

    /** A03/A04：plan_payload / 快照 execution_params → Plan.execution 投影。 */
    public Object execution(String rawPlanPayload) {
        return filter(rawPlanPayload, EXECUTION);
    }

    /** A01 / 快照 summary：plan_summary → SUMMARY 投影。 */
    public Object summary(String rawPlanSummary) {
        return filter(rawPlanSummary, SUMMARY);
    }

    /** A09：从 T07 plan_snapshot 取 summary 子对象并做 SUMMARY 投影。 */
    public Object summaryFromSnapshot(String rawPlanSnapshot) {
        JsonNode snapshot = readObject(rawPlanSnapshot);
        if (snapshot == null) {
            return null;
        }
        JsonNode summary = snapshot.get("summary");
        if (summary == null || !summary.isObject()) {
            return null;
        }
        return filter(summary, SUMMARY);
    }

    private JsonNode filter(String raw, Map<String, FieldType> whitelist) {
        return filter(readObject(raw), whitelist);
    }

    private JsonNode filter(JsonNode source, Map<String, FieldType> whitelist) {
        if (source == null || !source.isObject() || source.size() == 0) {
            return null;
        }
        ObjectNode out = objectMapper.createObjectNode();
        List<String> dropped = new ArrayList<>();
        source.fieldNames().forEachRemaining(name -> {
            FieldType type = whitelist.get(name);
            if (type == null || !matches(source.get(name), type)) {
                dropped.add(name);
                return;
            }
            out.set(name, source.get(name));
        });
        if (!dropped.isEmpty()) {
            // 仅记录被丢弃的键名，绝不记录值/内容
            log.warn("care plan projection dropped non-whitelisted keys: {}", dropped);
        }
        return out.size() == 0 ? null : out;
    }

    private static boolean matches(JsonNode value, FieldType type) {
        if (value == null || value.isNull()) {
            return false;
        }
        return switch (type) {
            case STRING -> value.isTextual();
            case ARRAY -> value.isArray();
            case OBJECT -> value.isObject();
        };
    }

    private JsonNode readObject(String raw) {
        if (raw == null || raw.isBlank() || "{}".equals(raw.trim())) {
            return null;
        }
        try {
            JsonNode node = objectMapper.readTree(raw);
            return node != null && node.isObject() && node.size() > 0 ? node : null;
        } catch (Exception parseFailure) {
            return null;
        }
    }

    private static Map<String, FieldType> whitelist(Object... pairs) {
        Map<String, FieldType> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < pairs.length; i += 2) {
            map.put((String) pairs[i], (FieldType) pairs[i + 1]);
        }
        return Map.copyOf(map);
    }
}

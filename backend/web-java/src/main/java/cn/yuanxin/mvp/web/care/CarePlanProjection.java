package cn.yuanxin.mvp.web.care;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * T06 方案 JSONB 的<b>递归结构化字段级白名单投影</b>（C 侧保守提案）。
 *
 * <p>背景：契约中 Plan.execution/plan_summary 为 {@code additionalProperties:true}
 * 的“结构未冻结”对象；整体透传会把供应商原始响应/提示词等敏感键泄露给客户端
 * 并冻结进 T07 快照。因此 C 侧对<b>每个层级</b>只放行已知语义字段，未知键与
 * 类型不符值一律丢弃（仅以 WARN 记录键路径，绝不记录值）。</p>
 *
 * <ul>
 *   <li>step 对象仅 {@code region(string) / parameters(object)}；</li>
 *   <li>parameter 定义：标量（string/number/boolean）原样；对象仅保留
 *       {@code value(标量) / unit(string)}；</li>
 *   <li>regions 数组仅保留 string 元素；</li>
 *   <li>parameters（顶层 object）：name → parameter 定义，递归同规则。</li>
 * </ul>
 * <p>任何层级过滤后为空对象/空数组 → 丢弃该键；顶层无白名单键残留 → 整体 null。
 * schema_version 属内部版本标记，不在任何白名单中，绝不外发。</p>
 *
 * <p><b>白名单为 C 侧保守提案，待总协调/D 契约确认后冻结</b>；协议未冻结字段
 * 保守省略，不发明任何设备参数。</p>
 */
@Component
public class CarePlanProjection {

    private static final Logger log = LoggerFactory.getLogger(CarePlanProjection.class);

    private enum Kind {
        STRING, STEPS, REGIONS, PARAMETERS
    }

    /** A02 Plan.full 白名单。 */
    private static final Map<String, Kind> FULL = whitelist(
            "title", Kind.STRING,
            "description", Kind.STRING,
            "steps", Kind.STEPS,
            "regions", Kind.REGIONS,
            "parameters", Kind.PARAMETERS);

    /** A03/A04 Plan.execution（快照 execution_params）白名单。 */
    private static final Map<String, Kind> EXECUTION = whitelist(
            "steps", Kind.STEPS,
            "regions", Kind.REGIONS,
            "parameters", Kind.PARAMETERS);

    /** A01/A03 快照 summary/A09 快照摘要白名单。 */
    private static final Map<String, Kind> SUMMARY = whitelist(
            "title", Kind.STRING,
            "description", Kind.STRING,
            "source_report_id", Kind.STRING,
            "source_report_ready_at", Kind.STRING);

    private final ObjectMapper objectMapper;

    public CarePlanProjection(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /** A02：plan_payload → Plan.full 投影（对象或 null）。 */
    public Object full(String rawPlanPayload) {
        return project(readObject(rawPlanPayload), FULL, "");
    }

    /** A03/A04：plan_payload / 快照 execution_params → Plan.execution 投影。 */
    public Object execution(String rawPlanPayload) {
        return project(readObject(rawPlanPayload), EXECUTION, "");
    }

    /** A01 / 快照 summary：plan_summary → SUMMARY 投影。 */
    public Object summary(String rawPlanSummary) {
        return project(readObject(rawPlanSummary), SUMMARY, "");
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
        return project(summary, SUMMARY, "summary");
    }

    private JsonNode project(JsonNode source, Map<String, Kind> whitelist, String path) {
        if (source == null || !source.isObject() || source.size() == 0) {
            return null;
        }
        ObjectNode out = objectMapper.createObjectNode();
        List<String> dropped = new ArrayList<>();
        source.fieldNames().forEachRemaining(name -> {
            String fieldPath = path.isEmpty() ? name : path + "." + name;
            Kind kind = whitelist.get(name);
            if (kind == null) {
                dropped.add(fieldPath);
                return;
            }
            JsonNode filtered = projectValue(source.get(name), kind, fieldPath, dropped);
            if (filtered != null) {
                out.set(name, filtered);
            }
        });
        warnDropped(dropped);
        return out.size() == 0 ? null : out;
    }

    private JsonNode projectValue(JsonNode value, Kind kind, String path, List<String> dropped) {
        if (value == null || value.isNull()) {
            dropped.add(path);
            return null;
        }
        return switch (kind) {
            case STRING -> value.isTextual() ? value : drop(dropped, path);
            case STEPS -> projectSteps(value, path, dropped);
            case REGIONS -> projectRegions(value, path, dropped);
            case PARAMETERS -> projectParameters(value, path, dropped);
        };
    }

    private JsonNode projectSteps(JsonNode value, String path, List<String> dropped) {
        if (!value.isArray()) {
            return drop(dropped, path);
        }
        ArrayNode out = objectMapper.createArrayNode();
        int index = 0;
        for (JsonNode step : value) {
            JsonNode filtered = projectStep(step, path + "[" + index + "]", dropped);
            if (filtered != null) {
                out.add(filtered);
            }
            index++;
        }
        return out.size() == 0 ? null : out;
    }

    private JsonNode projectStep(JsonNode step, String path, List<String> dropped) {
        if (step == null || !step.isObject()) {
            return drop(dropped, path);
        }
        ObjectNode out = objectMapper.createObjectNode();
        step.fieldNames().forEachRemaining(name -> {
            String fieldPath = path + "." + name;
            if ("region".equals(name)) {
                if (step.get(name).isTextual()) {
                    out.set("region", step.get(name));
                } else {
                    dropped.add(fieldPath);
                }
            } else if ("parameters".equals(name)) {
                JsonNode parameters = projectParameters(step.get(name), fieldPath, dropped);
                if (parameters != null) {
                    out.set("parameters", parameters);
                }
            } else {
                dropped.add(fieldPath);
            }
        });
        return out.size() == 0 ? null : out;
    }

    private JsonNode projectRegions(JsonNode value, String path, List<String> dropped) {
        if (!value.isArray()) {
            return drop(dropped, path);
        }
        ArrayNode out = objectMapper.createArrayNode();
        for (JsonNode element : value) {
            if (element.isTextual()) {
                out.add(element);
            } else {
                dropped.add(path + "[]");
            }
        }
        return out.size() == 0 ? null : out;
    }

    private JsonNode projectParameters(JsonNode value, String path, List<String> dropped) {
        if (!value.isObject()) {
            return drop(dropped, path);
        }
        ObjectNode out = objectMapper.createObjectNode();
        value.fieldNames().forEachRemaining(name -> {
            JsonNode parameter = projectParameter(value.get(name), path + "." + name, dropped);
            if (parameter != null) {
                out.set(name, parameter);
            }
        });
        return out.size() == 0 ? null : out;
    }

    private JsonNode projectParameter(JsonNode parameter, String path, List<String> dropped) {
        if (parameter == null || parameter.isNull()) {
            return drop(dropped, path);
        }
        if (isScalar(parameter)) {
            return parameter;
        }
        if (!parameter.isObject()) {
            return drop(dropped, path);
        }
        ObjectNode out = objectMapper.createObjectNode();
        parameter.fieldNames().forEachRemaining(name -> {
            JsonNode value = parameter.get(name);
            if ("value".equals(name)) {
                if (isScalar(value)) {
                    out.set("value", value);
                } else {
                    dropped.add(path + ".value");
                }
            } else if ("unit".equals(name)) {
                if (value.isTextual()) {
                    out.set("unit", value);
                } else {
                    dropped.add(path + ".unit");
                }
            } else {
                dropped.add(path + "." + name);
            }
        });
        return out.size() == 0 ? null : out;
    }

    private JsonNode drop(List<String> dropped, String path) {
        dropped.add(path);
        return null;
    }

    private static boolean isScalar(JsonNode value) {
        return value != null && (value.isTextual() || value.isNumber() || value.isBoolean());
    }

    private static void warnDropped(List<String> dropped) {
        if (!dropped.isEmpty()) {
            // 仅记录键路径，绝不记录值/内容
            log.warn("care plan projection dropped non-whitelisted keys: {}", dropped);
        }
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

    private static Map<String, Kind> whitelist(Object... pairs) {
        Map<String, Kind> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < pairs.length; i += 2) {
            map.put((String) pairs[i], (Kind) pairs[i + 1]);
        }
        return Map.copyOf(map);
    }
}

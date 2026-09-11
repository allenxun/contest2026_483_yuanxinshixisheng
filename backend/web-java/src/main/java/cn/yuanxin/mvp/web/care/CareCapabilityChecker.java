package cn.yuanxin.mvp.web.care;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * 准入能力覆盖判定（纯函数；无 I/O）。
 *
 * <p>对齐 D 侧版本化约定（总协调裁定 2026-09-11）：T06 {@code input_snapshot}
 * 形如
 * {@code {report:{assessment_id,report_id,report_photo_version}, capability:{microcrystal_id, capability_id, capability_revision, parameter_ranges, approved_regions, n_bounds}}}
 * （旧式 {@code required_capability_revision} 为虚构字段，已删除，不再参与任何
 * 放行/拒绝）。判定必须：当前可信设备能力同 {@code capability_id}、单位一致、
 * 实际参数值覆盖冻结参数范围、区域同时符合冻结 {@code approved_regions} 与当前
 * 设备支持区域、N 落在冻结 {@code n_bounds} 内。</p>
 *
 * <p><b>capability_revision 仅作追溯，绝不参与放行/拒绝；microcrystal_id 仅标记
 * 方案生成来源，不锁定执行设备</b>（裁定原文）。C 侧对 D 约定做防御式读取，
 * 形状差异报协调、不擅改。</p>
 */
@Component
public class CareCapabilityChecker {

    /** 有界 reason token（公开给测试与调用方）。 */
    public static final String DEVICE_CAPABILITIES_MISSING = "device_capabilities_missing";
    public static final String FROZEN_CAPABILITY_MISSING = "frozen_capability_requirement_missing";
    public static final String CAPABILITY_ID_MISMATCH = "capability_id_mismatch";
    public static final String PARAMETER_RANGE_NOT_COVERED = "parameter_range_not_covered";
    public static final String REGION_NOT_SUPPORTED = "region_not_supported";
    public static final String N_OUT_OF_BOUNDS = "n_out_of_bounds";
    public static final String STEP_PARAMETERS_NOT_COVERED = "step_parameters_not_covered";
    public static final String MALFORMED_FROZEN_STEP = "malformed_frozen_step";

    private final ObjectMapper objectMapper;

    public CareCapabilityChecker(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * @return {@code empty} = 冻结需求已被当前设备能力覆盖；否则为首个不符的有界
     *         reason token（调用方映射为 409 PLAN_NOT_READY details.reason）。
     */
    public Optional<String> notCoveredReason(String inputSnapshotJson, String planPayloadJson,
                                             Long targetCount, String capabilitiesJson) {
        JsonNode device = readObject(capabilitiesJson);
        if (device == null) {
            return Optional.of(DEVICE_CAPABILITIES_MISSING);
        }
        JsonNode snapshot = readObject(inputSnapshotJson);
        JsonNode capability = snapshot == null ? null : asObject(snapshot.get("capability"));
        if (capability == null) {
            return Optional.of(FROZEN_CAPABILITY_MISSING);
        }

        // 3) capability_id：冻结值为非空字符串时必须与设备一致
        String frozenCapabilityId = text(capability, "capability_id");
        if (frozenCapabilityId != null && !frozenCapabilityId.isEmpty()
                && !frozenCapabilityId.equals(text(device, "capability_id"))) {
            return Optional.of(CAPABILITY_ID_MISMATCH);
        }

        // 4) 冻结参数范围逐项必须被设备更宽（含端点）且单位一致覆盖
        JsonNode frozenRanges = asObject(capability.get("parameter_ranges"));
        JsonNode deviceRanges = asObject(device.get("parameter_ranges"));
        if (frozenRanges != null) {
            for (String name : fieldNames(frozenRanges)) {
                if (!rangeCovers(deviceRanges, frozenRanges, name)) {
                    return Optional.of(PARAMETER_RANGE_NOT_COVERED);
                }
            }
        }

        // 5) 冻结 approved_regions ⊆ 设备支持区域（supported_regions，回退 regions）
        List<String> approvedRegions = stringList(capability.get("approved_regions"));
        Set<String> deviceRegions = deviceRegionSet(device);
        if (deviceRegions == null) {
            return Optional.of(REGION_NOT_SUPPORTED);
        }
        if (approvedRegions != null) {
            for (String region : approvedRegions) {
                if (!deviceRegions.contains(region)) {
                    return Optional.of(REGION_NOT_SUPPORTED);
                }
            }
        }

        // 6) n_bounds 存在时 N 必须落在闭区间内
        JsonNode nBounds = asObject(capability.get("n_bounds"));
        if (nBounds != null) {
            BigDecimal min = decimal(nBounds.get("min"));
            BigDecimal max = decimal(nBounds.get("max"));
            if (min == null || max == null || targetCount == null) {
                return Optional.of(N_OUT_OF_BOUNDS);
            }
            BigDecimal n = BigDecimal.valueOf(targetCount);
            if (n.compareTo(min) < 0 || n.compareTo(max) > 0) {
                return Optional.of(N_OUT_OF_BOUNDS);
            }
        }

        // 7) 冻结 steps：region 与参数须同时落在冻结与设备约束内
        JsonNode steps = planPayload(planPayloadJson);
        if (steps != null) {
            for (JsonNode step : steps) {
                String failure = checkStep(step, frozenRanges, deviceRanges, approvedRegions,
                        deviceRegions);
                if (failure != null) {
                    return Optional.of(failure);
                }
            }
        }
        return Optional.empty();
    }

    private String checkStep(JsonNode step, JsonNode frozenRanges, JsonNode deviceRanges,
                             List<String> approvedRegions, Set<String> deviceRegions) {
        if (step == null || !step.isObject()) {
            return MALFORMED_FROZEN_STEP;
        }
        JsonNode regionNode = step.get("region");
        if (regionNode != null && !regionNode.isNull()) {
            if (!regionNode.isTextual()) {
                return MALFORMED_FROZEN_STEP;
            }
            String region = regionNode.asText();
            if (approvedRegions == null || !approvedRegions.contains(region)
                    || !deviceRegions.contains(region)) {
                return STEP_PARAMETERS_NOT_COVERED;
            }
        }
        JsonNode parameters = step.get("parameters");
        if (parameters == null || parameters.isNull()) {
            return null;
        }
        if (!parameters.isObject()) {
            return MALFORMED_FROZEN_STEP;
        }
        for (String name : fieldNames(parameters)) {
            JsonNode raw = parameters.get(name);
            BigDecimal value;
            String unit = null;
            if (raw != null && raw.isObject()) {
                value = decimal(raw.get("value"));
                unit = text(raw, "unit");
            } else {
                value = decimal(raw);
            }
            if (value == null) {
                return STEP_PARAMETERS_NOT_COVERED;
            }
            if (!valueWithin(frozenRanges, name, value) || !valueWithin(deviceRanges, name, value)) {
                return STEP_PARAMETERS_NOT_COVERED;
            }
            if (unit != null) {
                String frozenUnit = rangeUnit(frozenRanges, name);
                String deviceUnit = rangeUnit(deviceRanges, name);
                if ((frozenUnit != null && !unit.equals(frozenUnit))
                        || (deviceUnit != null && !unit.equals(deviceUnit))) {
                    return STEP_PARAMETERS_NOT_COVERED;
                }
            }
        }
        return null;
    }

    private boolean rangeCovers(JsonNode deviceRanges, JsonNode frozenRanges, String name) {
        JsonNode frozen = asObject(frozenRanges.get(name));
        JsonNode device = deviceRanges == null ? null : asObject(deviceRanges.get(name));
        if (frozen == null || device == null) {
            return false;
        }
        BigDecimal frozenMin = decimal(frozen.get("min"));
        BigDecimal frozenMax = decimal(frozen.get("max"));
        BigDecimal deviceMin = decimal(device.get("min"));
        BigDecimal deviceMax = decimal(device.get("max"));
        if (frozenMin == null || frozenMax == null || deviceMin == null || deviceMax == null) {
            return false;
        }
        String frozenUnit = text(frozen, "unit");
        String deviceUnit = text(device, "unit");
        if (frozenUnit != null && deviceUnit != null && !frozenUnit.equals(deviceUnit)) {
            return false;
        }
        return deviceMin.compareTo(frozenMin) <= 0 && deviceMax.compareTo(frozenMax) >= 0;
    }

    private boolean valueWithin(JsonNode ranges, String name, BigDecimal value) {
        JsonNode range = ranges == null ? null : asObject(ranges.get(name));
        if (range == null) {
            return false;
        }
        BigDecimal min = decimal(range.get("min"));
        BigDecimal max = decimal(range.get("max"));
        return min != null && max != null
                && value.compareTo(min) >= 0 && value.compareTo(max) <= 0;
    }

    private String rangeUnit(JsonNode ranges, String name) {
        JsonNode range = ranges == null ? null : asObject(ranges.get(name));
        return range == null ? null : text(range, "unit");
    }

    private JsonNode planPayload(String planPayloadJson) {
        JsonNode payload = readObject(planPayloadJson);
        if (payload == null) {
            return null;
        }
        JsonNode steps = payload.get("steps");
        return steps != null && steps.isArray() ? steps : null;
    }

    private Set<String> deviceRegionSet(JsonNode device) {
        List<String> regions = stringList(device.get("supported_regions"));
        if (regions == null) {
            regions = stringList(device.get("regions"));
        }
        return regions == null ? null : new LinkedHashSet<>(regions);
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

    private static JsonNode asObject(JsonNode node) {
        return node != null && node.isObject() ? node : null;
    }

    private static String text(JsonNode parent, String name) {
        if (parent == null) {
            return null;
        }
        JsonNode value = parent.get(name);
        return value != null && value.isTextual() ? value.asText() : null;
    }

    private static List<String> fieldNames(JsonNode object) {
        List<String> names = new ArrayList<>();
        object.fieldNames().forEachRemaining(names::add);
        return names;
    }

    private static List<String> stringList(JsonNode node) {
        if (node == null || !node.isArray()) {
            return null;
        }
        List<String> out = new ArrayList<>();
        for (JsonNode item : node) {
            if (!item.isTextual()) {
                return null;
            }
            out.add(item.asText());
        }
        return out;
    }

    private static BigDecimal decimal(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        if (node.isNumber()) {
            return node.decimalValue();
        }
        if (node.isTextual()) {
            try {
                return new BigDecimal(node.asText());
            } catch (NumberFormatException invalid) {
                return null;
            }
        }
        return null;
    }
}

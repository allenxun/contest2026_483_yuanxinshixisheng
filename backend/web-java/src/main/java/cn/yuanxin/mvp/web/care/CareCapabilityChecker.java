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
 * <p>对齐 D 侧版本化约定（总协调裁定 2026-09-11）：
 * T06 {@code input_snapshot} 形如
 * {@code {report:{...}, capability:{capability_id, capability_revision, parameter_ranges, approved_regions, n_bounds}}}
 * （旧式 {@code required_capability_revision} 为虚构字段，已删除）。判定
 * <b>fail-closed</b>：冻结块必需子结构任一缺失/畸形即拒绝，绝不当“无要求”跳过；
 * 当前可信设备能力必须同 {@code capability_id}、双侧单位严格相等且存在、设备参数范围
 * 覆盖冻结范围、区域同时符合冻结 {@code approved_regions} 与设备支持区域、N 落在
 * 冻结 {@code n_bounds} 内、冻结 steps 的 region/参数被双重覆盖。</p>
 *
 * <p>steps 协议尚未在契约冻结，故 {@code plan_payload.steps} 缺失/非数组/空数组以及
 * step 缺 {@code region} 或 {@code parameters} 非对象一律保守拒绝
 * ({@link #MALFORMED_FROZEN_STEP})，不猜测缺省语义。</p>
 *
 * <p><b>capability_revision / microcrystal_id 绝不参与放行或拒绝</b>（前者仅追溯，
 * 后者仅标记方案生成来源，不锁定执行设备）。C 侧对 D 约定做防御式读取，形状差异
 * 报协调、不擅改。</p>
 */
@Component
public class CareCapabilityChecker {

    /** 有界 reason token（公开给测试与调用方）。 */
    public static final String DEVICE_CAPABILITIES_MISSING = "device_capabilities_missing";
    public static final String FROZEN_CAPABILITY_MISSING = "frozen_capability_requirement_missing";
    public static final String MALFORMED_FROZEN_CAPABILITY = "malformed_frozen_capability";
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
        Optional<String> malformed = validateFrozenCapability(capability);
        if (malformed.isPresent()) {
            return malformed;
        }

        String frozenCapabilityId = text(capability, "capability_id");
        String deviceCapabilityId = text(device, "capability_id");
        if (deviceCapabilityId == null || !frozenCapabilityId.equals(deviceCapabilityId)) {
            return Optional.of(CAPABILITY_ID_MISMATCH);
        }

        JsonNode frozenRanges = capability.get("parameter_ranges");
        JsonNode deviceRanges = asObject(device.get("parameter_ranges"));
        if (deviceRanges == null) {
            return Optional.of(PARAMETER_RANGE_NOT_COVERED);
        }
        for (String name : fieldNames(frozenRanges)) {
            if (!rangeCovers(deviceRanges, frozenRanges, name)) {
                return Optional.of(PARAMETER_RANGE_NOT_COVERED);
            }
        }

        List<String> approvedRegions = stringList(capability.get("approved_regions"));
        Set<String> deviceRegions = deviceRegionSet(device);
        if (deviceRegions == null) {
            return Optional.of(REGION_NOT_SUPPORTED);
        }
        for (String region : approvedRegions) {
            if (!deviceRegions.contains(region)) {
                return Optional.of(REGION_NOT_SUPPORTED);
            }
        }

        JsonNode nBounds = capability.get("n_bounds");
        BigDecimal nMin = decimal(nBounds.get("min"));
        BigDecimal nMax = decimal(nBounds.get("max"));
        if (targetCount == null) {
            return Optional.of(N_OUT_OF_BOUNDS);
        }
        BigDecimal n = BigDecimal.valueOf(targetCount);
        if (n.compareTo(nMin) < 0 || n.compareTo(nMax) > 0) {
            return Optional.of(N_OUT_OF_BOUNDS);
        }

        return checkSteps(planPayloadJson, frozenRanges, deviceRanges, approvedRegions,
                deviceRegions);
    }

    private Optional<String> validateFrozenCapability(JsonNode capability) {
        JsonNode capabilityId = capability.get("capability_id");
        if (capabilityId == null || !capabilityId.isTextual() || capabilityId.asText().isBlank()) {
            return Optional.of(MALFORMED_FROZEN_CAPABILITY);
        }
        JsonNode ranges = asObject(capability.get("parameter_ranges"));
        if (ranges == null || ranges.size() == 0) {
            return Optional.of(MALFORMED_FROZEN_CAPABILITY);
        }
        for (String name : fieldNames(ranges)) {
            JsonNode range = asObject(ranges.get(name));
            if (range == null) {
                return Optional.of(MALFORMED_FROZEN_CAPABILITY);
            }
            BigDecimal min = decimal(range.get("min"));
            BigDecimal max = decimal(range.get("max"));
            if (min == null || max == null || min.compareTo(max) > 0) {
                return Optional.of(MALFORMED_FROZEN_CAPABILITY);
            }
            String unit = text(range, "unit");
            if (unit == null || unit.isBlank()) {
                return Optional.of(MALFORMED_FROZEN_CAPABILITY);
            }
        }
        List<String> approved = stringList(capability.get("approved_regions"));
        if (approved == null || approved.isEmpty()) {
            return Optional.of(MALFORMED_FROZEN_CAPABILITY);
        }
        JsonNode nBounds = asObject(capability.get("n_bounds"));
        if (nBounds == null) {
            return Optional.of(MALFORMED_FROZEN_CAPABILITY);
        }
        BigDecimal nMin = decimal(nBounds.get("min"));
        BigDecimal nMax = decimal(nBounds.get("max"));
        if (nMin == null || nMax == null || nMin.compareTo(nMax) > 0) {
            return Optional.of(MALFORMED_FROZEN_CAPABILITY);
        }
        return Optional.empty();
    }

    private Optional<String> checkSteps(String planPayloadJson, JsonNode frozenRanges,
                                        JsonNode deviceRanges, List<String> approvedRegions,
                                        Set<String> deviceRegions) {
        JsonNode payload = readObject(planPayloadJson);
        JsonNode steps = payload == null ? null : payload.get("steps");
        if (steps == null || !steps.isArray() || steps.size() == 0) {
            return Optional.of(MALFORMED_FROZEN_STEP);
        }
        for (JsonNode step : steps) {
            Optional<String> failure = checkStep(step, frozenRanges, deviceRanges, approvedRegions,
                    deviceRegions);
            if (failure.isPresent()) {
                return failure;
            }
        }
        return Optional.empty();
    }

    private Optional<String> checkStep(JsonNode step, JsonNode frozenRanges, JsonNode deviceRanges,
                                       List<String> approvedRegions, Set<String> deviceRegions) {
        if (step == null || !step.isObject()) {
            return Optional.of(MALFORMED_FROZEN_STEP);
        }
        JsonNode regionNode = step.get("region");
        if (regionNode == null || !regionNode.isTextual() || regionNode.asText().isBlank()) {
            return Optional.of(MALFORMED_FROZEN_STEP);
        }
        JsonNode parameters = step.get("parameters");
        if (parameters == null || !parameters.isObject()) {
            return Optional.of(MALFORMED_FROZEN_STEP);
        }
        String region = regionNode.asText();
        if (!approvedRegions.contains(region) || !deviceRegions.contains(region)) {
            return Optional.of(REGION_NOT_SUPPORTED);
        }
        for (String name : fieldNames(parameters)) {
            if (frozenRanges.get(name) == null) {
                return Optional.of(STEP_PARAMETERS_NOT_COVERED);
            }
            JsonNode raw = parameters.get(name);
            BigDecimal value;
            String unit = null;
            if (raw != null && raw.isObject()) {
                value = decimal(raw.get("value"));
                unit = text(raw, "unit");
            } else if (isScalar(raw)) {
                value = decimal(raw);
            } else {
                value = null;
            }
            if (value == null) {
                return Optional.of(STEP_PARAMETERS_NOT_COVERED);
            }
            if (!valueWithin(frozenRanges, name, value) || !valueWithin(deviceRanges, name, value)) {
                return Optional.of(STEP_PARAMETERS_NOT_COVERED);
            }
            if (raw != null && raw.isObject()) {
                String frozenUnit = rangeUnit(frozenRanges, name);
                if (unit == null || !unit.equals(frozenUnit)) {
                    return Optional.of(STEP_PARAMETERS_NOT_COVERED);
                }
            }
        }
        return Optional.empty();
    }

    private boolean rangeCovers(JsonNode deviceRanges, JsonNode frozenRanges, String name) {
        JsonNode frozen = asObject(frozenRanges.get(name));
        JsonNode device = asObject(deviceRanges.get(name));
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
        // 双侧 unit 都必须存在且严格相等
        if (frozenUnit == null || deviceUnit == null || !frozenUnit.equals(deviceUnit)) {
            return false;
        }
        return deviceMin.compareTo(frozenMin) <= 0 && deviceMax.compareTo(frozenMax) >= 0;
    }

    private boolean valueWithin(JsonNode ranges, String name, BigDecimal value) {
        JsonNode range = asObject(ranges.get(name));
        if (range == null) {
            return false;
        }
        BigDecimal min = decimal(range.get("min"));
        BigDecimal max = decimal(range.get("max"));
        return min != null && max != null
                && value.compareTo(min) >= 0 && value.compareTo(max) <= 0;
    }

    private String rangeUnit(JsonNode ranges, String name) {
        JsonNode range = asObject(ranges.get(name));
        return range == null ? null : text(range, "unit");
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

    private static boolean isScalar(JsonNode node) {
        return node != null && (node.isTextual() || node.isNumber() || node.isBoolean());
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

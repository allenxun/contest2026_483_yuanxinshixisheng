package cn.yuanxin.mvp.web.care;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link CareCapabilityChecker} 纯单元测试（无 Spring / 无 PG）：全部分支与边界。
 * 字段形状取自 D 版本化约定；capability_revision 与 microcrystal_id 不作放行证据。
 */
class CareCapabilityCheckerTest {

    private static final CareCapabilityChecker CHECKER =
            new CareCapabilityChecker(new ObjectMapper());

    private static final String STEPS =
            "{\"schema_version\":1,\"title\":\"t\",\"steps\":[{\"region\":\"face\","
                    + "\"parameters\":{\"intensity\":\"3\"}}]}";
    private static final String NO_STEPS = "{\"schema_version\":1,\"title\":\"t\"}";

    private static String frozen(String capabilityJson) {
        return "{\"schema_version\":1,\"capability\":" + capabilityJson + "}";
    }

    private static String capability(String capabilityId, String min, String max, String unit,
                                     String approvedRegions, String nMin, String nMax) {
        StringBuilder sb = new StringBuilder("{\"microcrystal_id\":\"mc-frozen\",\"capability_id\":");
        sb.append(capabilityId == null ? "null" : "\"" + capabilityId + "\"");
        sb.append(",\"capability_revision\":\"7\",\"parameter_ranges\":{\"intensity\":{")
                .append("\"min\":\"").append(min).append("\",\"max\":\"").append(max).append("\"");
        if (unit != null) {
            sb.append(",\"unit\":\"").append(unit).append("\"");
        }
        sb.append("}}");
        if (approvedRegions != null) {
            sb.append(",\"approved_regions\":").append(approvedRegions);
        }
        if (nMin != null && nMax != null) {
            sb.append(",\"n_bounds\":{\"min\":\"").append(nMin).append("\",\"max\":\"")
                    .append(nMax).append("\"}");
        }
        return sb.append('}').toString();
    }

    private static String device(String capabilityId, String min, String max, String unit,
                                 String regionsKey, String regionsJson) {
        StringBuilder sb = new StringBuilder("{\"schema_version\":1,\"capability_id\":");
        sb.append(capabilityId == null ? "null" : "\"" + capabilityId + "\"");
        sb.append(",\"revision\":\"9\",\"parameter_ranges\":{\"intensity\":{")
                .append("\"min\":\"").append(min).append("\",\"max\":\"").append(max).append("\"");
        if (unit != null) {
            sb.append(",\"unit\":\"").append(unit).append("\"");
        }
        sb.append("}}");
        if (regionsJson != null) {
            sb.append(",\"").append(regionsKey).append("\":").append(regionsJson);
        }
        return sb.append('}').toString();
    }

    private static Optional<String> check(String snapshot, String payload, Long n, String deviceJson) {
        return CHECKER.notCoveredReason(snapshot, payload, n, deviceJson);
    }

    private static String covered(String snapshot, String payload, Long n, String deviceJson) {
        return check(snapshot, payload, n, deviceJson).orElse(null);
    }

    @Test
    @DisplayName("默认冻结/设备组合在 N=5、steps face 下覆盖")
    void coveredDefault() {
        assertTrue(check(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, STEPS, 5L,
                CareTestFixtures.DEFAULT_CAPABILITIES).isEmpty());
    }

    @Test
    @DisplayName("设备能力缺失 → device_capabilities_missing")
    void deviceMissing() {
        assertEquals(CareCapabilityChecker.DEVICE_CAPABILITIES_MISSING,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, "{}"));
    }

    @Test
    @DisplayName("snapshot 无 capability 块/非对象 → frozen_capability_requirement_missing")
    void frozenMissing() {
        assertEquals(CareCapabilityChecker.FROZEN_CAPABILITY_MISSING,
                covered("{\"schema_version\":1,\"report\":{}}", STEPS, 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));
        assertEquals(CareCapabilityChecker.FROZEN_CAPABILITY_MISSING,
                covered("{\"schema_version\":1,\"capability\":[]}", STEPS, 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));
    }

    @Test
    @DisplayName("capability_id 不符 → capability_id_mismatch")
    void capabilityIdMismatch() {
        assertEquals(CareCapabilityChecker.CAPABILITY_ID_MISMATCH,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device("cap-other", "0", "8", "level", "supported_regions",
                                "[\"face\"]")));
    }

    @Test
    @DisplayName("冻结缺 capability_id → malformed_frozen_capability（fail-closed）")
    void capabilityIdAbsentFrozen() {
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_CAPABILITY,
                covered(frozen(capability(null, "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device(null, "0", "8", "level", "supported_regions",
                                "[\"face\"]")));
    }

    @Test
    @DisplayName("单位不一致 → parameter_range_not_covered")
    void unitMismatch() {
        assertEquals(CareCapabilityChecker.PARAMETER_RANGE_NOT_COVERED,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device("cap-mvp-1", "0", "8", "step", "supported_regions",
                                "[\"face\"]")));
    }

    @Test
    @DisplayName("设备范围更窄（max/min）→ parameter_range_not_covered")
    void deviceRangeNarrower() {
        assertEquals(CareCapabilityChecker.PARAMETER_RANGE_NOT_COVERED,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device("cap-mvp-1", "0", "3", "level", "supported_regions",
                                "[\"face\"]")));
        assertEquals(CareCapabilityChecker.PARAMETER_RANGE_NOT_COVERED,
                covered(frozen(capability("cap-mvp-1", "2", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device("cap-mvp-1", "3", "8", "level", "supported_regions",
                                "[\"face\"]")));
    }

    @Test
    @DisplayName("设备缺同名参数项 → parameter_range_not_covered")
    void missingDeviceParameter() {
        assertEquals(CareCapabilityChecker.PARAMETER_RANGE_NOT_COVERED,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, "{\"schema_version\":1,\"capability_id\":\"cap-mvp-1\","
                                + "\"parameter_ranges\":{},\"supported_regions\":[\"face\"]}"));
    }

    @Test
    @DisplayName("冻结 approved_regions 不在设备支持区域 → region_not_supported")
    void regionNotSupported() {
        assertEquals(CareCapabilityChecker.REGION_NOT_SUPPORTED,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device("cap-mvp-1", "0", "8", "level", "supported_regions",
                                "[\"neck\"]")));
    }

    @Test
    @DisplayName("设备区域键回退 regions；两者皆无 → region_not_supported")
    void regionFallback() {
        assertTrue(check(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                STEPS, 5L, device("cap-mvp-1", "0", "8", "level", "regions", "[\"face\"]"))
                .isEmpty());
        assertEquals(CareCapabilityChecker.REGION_NOT_SUPPORTED,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device("cap-mvp-1", "0", "8", "level", "supported_regions", null)));
    }

    @Test
    @DisplayName("N 越 n_bounds 两端 → n_out_of_bounds；含端点通过")
    void nBounds() {
        String snapshot = CareTestFixtures.DEFAULT_INPUT_SNAPSHOT;
        String device = CareTestFixtures.DEFAULT_CAPABILITIES;
        assertTrue(check(snapshot, STEPS, 1L, device).isEmpty());
        assertTrue(check(snapshot, STEPS, 30L, device).isEmpty());
        assertEquals(CareCapabilityChecker.N_OUT_OF_BOUNDS, covered(snapshot, STEPS, 0L, device));
        assertEquals(CareCapabilityChecker.N_OUT_OF_BOUNDS, covered(snapshot, STEPS, 31L, device));
        assertEquals(CareCapabilityChecker.N_OUT_OF_BOUNDS, covered(snapshot, STEPS, null, device));
    }

    @Test
    @DisplayName("capability_revision(9≠7) 与 microcrystal_id 差异不作放行/拒绝证据")
    void revisionAndMicrocrystalNotGating() {
        assertTrue(check(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, STEPS, 5L,
                CareTestFixtures.DEFAULT_CAPABILITIES).isEmpty());
    }

    @Test
    @DisplayName("step.region 不在冻结 approved_regions/设备支持 → region_not_supported")
    void stepRegionNotCovered() {
        String payload = "{\"steps\":[{\"region\":\"arm\",\"parameters\":{}}]}";
        assertEquals(CareCapabilityChecker.REGION_NOT_SUPPORTED,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, payload, 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));
    }

    @Test
    @DisplayName("step 参数越冻结界/越设备界 → step_parameters_not_covered")
    void stepParameterBounds() {
        String aboveFrozen = "{\"steps\":[{\"region\":\"face\","
                + "\"parameters\":{\"intensity\":\"6\"}}]}";
        assertEquals(CareCapabilityChecker.STEP_PARAMETERS_NOT_COVERED,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, aboveFrozen, 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));

        String deviceRange = device("cap-mvp-1", "0", "2", "level", "supported_regions",
                "[\"face\"]");
        String withinDeviceButNotFrozen = "{\"steps\":[{\"region\":\"face\","
                + "\"parameters\":{\"intensity\":\"4\"}}]}";
        assertTrue(check(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, withinDeviceButNotFrozen, 5L,
                deviceRange).isPresent());
    }

    @Test
    @DisplayName("step 形状非法 → malformed_frozen_step")
    void malformedStep() {
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_STEP,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, "{\"steps\":[42]}", 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));
    }

    @Test
    @DisplayName("step 参数 {value,unit} 形式：值在界内且单位一致 → 覆盖；单位不符 → 不覆盖")
    void stepValueObjectUnit() {
        String ok = "{\"steps\":[{\"region\":\"face\",\"parameters\":{"
                + "\"intensity\":{\"value\":\"3\",\"unit\":\"level\"}}}]}";
        assertTrue(check(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, ok, 5L,
                CareTestFixtures.DEFAULT_CAPABILITIES).isEmpty());
        String badUnit = "{\"steps\":[{\"region\":\"face\",\"parameters\":{"
                + "\"intensity\":{\"value\":\"3\",\"unit\":\"step\"}}}]}";
        assertEquals(CareCapabilityChecker.STEP_PARAMETERS_NOT_COVERED,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, badUnit, 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));
    }

    @Test
    @DisplayName("BigDecimal 小数比较（含等值不同表示）")
    void decimalComparison() {
        String snapshot = frozen(capability("cap-mvp-1", "0", "5.5", "level", "[\"face\"]",
                "1", "30"));
        String device = device("cap-mvp-1", "0", "5.50", "level", "supported_regions",
                "[\"face\"]");
        String payload = "{\"steps\":[{\"region\":\"face\",\"parameters\":{"
                + "\"intensity\":\"5.25\"}}]}";
        assertTrue(check(snapshot, payload, 5L, device).isEmpty());
        String above = "{\"steps\":[{\"region\":\"face\",\"parameters\":{"
                + "\"intensity\":\"5.6\"}}]}";
        assertEquals(CareCapabilityChecker.STEP_PARAMETERS_NOT_COVERED,
                covered(snapshot, above, 5L, device));
    }

    @Test
    @DisplayName("payload 无 steps / steps=[] / step 缺 region → malformed_frozen_step（fail-closed）")
    void noSteps() {
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_STEP,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, NO_STEPS, 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_STEP,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT, "{\"steps\":[]}", 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_STEP,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT,
                        "{\"steps\":[{\"parameters\":{}}]}", 5L,
                        CareTestFixtures.DEFAULT_CAPABILITIES));
    }

    @Test
    @DisplayName("严格 fail-closed 负例合集：冻结子结构缺失/畸形、设备缺失、step 参数未知")
    void strictFailClosedNegativeCases() {
        String deviceValid = CareTestFixtures.DEFAULT_CAPABILITIES;
        String fullRanges = "\"parameter_ranges\":{\"intensity\":{\"min\":\"0\",\"max\":\"5\","
                + "\"unit\":\"level\"}}";

        // capability={} → malformed_frozen_capability
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_CAPABILITY,
                covered(frozen("{}"), STEPS, 5L, deviceValid));
        // 缺 capability_id
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_CAPABILITY,
                covered(frozen("{" + fullRanges + ",\"approved_regions\":[\"face\"],"
                        + "\"n_bounds\":{\"min\":\"1\",\"max\":\"30\"}}"), STEPS, 5L, deviceValid));
        // 缺 parameter_ranges
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_CAPABILITY,
                covered(frozen("{\"capability_id\":\"cap-mvp-1\",\"approved_regions\":[\"face\"],"
                        + "\"n_bounds\":{\"min\":\"1\",\"max\":\"30\"}}"), STEPS, 5L, deviceValid));
        // 缺 approved_regions
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_CAPABILITY,
                covered(frozen("{\"capability_id\":\"cap-mvp-1\"," + fullRanges
                        + ",\"n_bounds\":{\"min\":\"1\",\"max\":\"30\"}}"), STEPS, 5L, deviceValid));
        // 缺 n_bounds
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_CAPABILITY,
                covered(frozen("{\"capability_id\":\"cap-mvp-1\"," + fullRanges
                        + ",\"approved_regions\":[\"face\"]}"), STEPS, 5L, deviceValid));
        // 冻结缺 unit
        assertEquals(CareCapabilityChecker.MALFORMED_FROZEN_CAPABILITY,
                covered(frozen(capability("cap-mvp-1", "0", "5", null, "[\"face\"]", "1", "30")),
                        STEPS, 5L, deviceValid));
        // 设备缺 unit
        assertEquals(CareCapabilityChecker.PARAMETER_RANGE_NOT_COVERED,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device("cap-mvp-1", "0", "8", null, "supported_regions",
                                "[\"face\"]")));
        // 设备缺 parameter_ranges
        assertEquals(CareCapabilityChecker.PARAMETER_RANGE_NOT_COVERED,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, "{\"schema_version\":1,\"capability_id\":\"cap-mvp-1\","
                                + "\"supported_regions\":[\"face\"]}"));
        // 设备 capability_id 缺失
        assertEquals(CareCapabilityChecker.CAPABILITY_ID_MISMATCH,
                covered(frozen(capability("cap-mvp-1", "0", "5", "level", "[\"face\"]", "1", "30")),
                        STEPS, 5L, device(null, "0", "8", "level", "supported_regions",
                                "[\"face\"]")));
        // step 参数名不在冻结 ranges
        assertEquals(CareCapabilityChecker.STEP_PARAMETERS_NOT_COVERED,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT,
                        "{\"steps\":[{\"region\":\"face\",\"parameters\":{\"unknown\":\"1\"}}]}", 5L,
                        deviceValid));
        // step 参数 {value,unit} 缺 unit（对象形式必须给出 unit）
        assertEquals(CareCapabilityChecker.STEP_PARAMETERS_NOT_COVERED,
                covered(CareTestFixtures.DEFAULT_INPUT_SNAPSHOT,
                        "{\"steps\":[{\"region\":\"face\",\"parameters\":{"
                                + "\"intensity\":{\"value\":\"3\"}}}]}", 5L, deviceValid));
    }
}

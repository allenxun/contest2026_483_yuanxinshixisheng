package cn.yuanxin.mvp.web.devices;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 设备包内部 JSON/JSONB 辅助：宽松读取（DB 里的 {@code '{}'} 占位与缺键都
 * 容忍）与普通写入（JSONB 是内部诊断/观测形状，不需要 JCS 规范化）。
 *
 * <p>注意：写入 JSONB 时 {@code schema_version} 必须以 JSON 整数出现
 * （V1 列的 {@code jsonb_typeof(...)='number'} CHECK）——调用方负责放入
 * {@code int}/{@code long} 而不是字符串。</p>
 */
public final class DeviceJson {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final TypeReference<Map<String, Object>> MAP_TYPE =
            new TypeReference<Map<String, Object>>() {
            };

    private DeviceJson() {
    }

    /** 解析 JSON 对象；空/非法/非对象一律返回空 Map（不抛，容错旧占位）。 */
    public static Map<String, Object> parseObject(String raw) {
        if (raw == null || raw.isBlank()) {
            return new LinkedHashMap<>();
        }
        try {
            Map<String, Object> value = MAPPER.readValue(raw, MAP_TYPE);
            return value == null ? new LinkedHashMap<>() : value;
        } catch (Exception e) {
            return new LinkedHashMap<>();
        }
    }

    public static String write(Object value) {
        try {
            return MAPPER.writeValueAsString(value);
        } catch (Exception e) {
            throw new IllegalStateException("device json serialization failed", e);
        }
    }

    /** 取嵌套对象；非对象/缺键返回空 Map。 */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> objectAt(Map<String, Object> map, String key) {
        Object v = map.get(key);
        if (v instanceof Map<?, ?> m) {
            return (Map<String, Object>) m;
        }
        return new LinkedHashMap<>();
    }

    public static String textAt(Map<String, Object> map, String key) {
        Object v = map.get(key);
        return v instanceof String s ? s : null;
    }

    public static Long longAt(Map<String, Object> map, String key) {
        Object v = map.get(key);
        if (v instanceof Number n) {
            return n.longValue();
        }
        if (v instanceof String s) {
            try {
                return Long.parseLong(s);
            } catch (NumberFormatException e) {
                return null;
            }
        }
        return null;
    }

    /** 浅拷贝 episode 映射（值对象元素再复制一层，避免共享可变 Map）。 */
    public static Map<String, Object> copyEpisodeMap(Map<String, Object> source) {
        Map<String, Object> copy = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : source.entrySet()) {
            if (e.getValue() instanceof Map<?, ?> m) {
                Map<String, Object> inner = new LinkedHashMap<>();
                m.forEach((k, v) -> inner.put(String.valueOf(k), v));
                copy.put(e.getKey(), inner);
            } else {
                copy.put(e.getKey(), e.getValue());
            }
        }
        return copy;
    }
}

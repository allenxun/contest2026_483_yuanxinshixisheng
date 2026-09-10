package cn.yuanxin.mvp.web.idempotency;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;

/**
 * RFC 8785 (JCS) 序列化 + SHA-256 payload_hash（contracts/canonicalization.md）。
 *
 * <p><b>行为锁定基准是 backend/contracts/scripts/jcs.py</b>（跨语言唯一参考
 * 实现，两侧测试必须字节一致复现 samples/canonicalization/vectors.json 全部
 * 向量）。实现要点：</p>
 * <ul>
 *   <li>对象键按 UTF-16 code unit 升序（Java String.compareTo 即该顺序）；
 *       数组保持原序；无空白；</li>
 *   <li>字符串最小转义（" \ \b \t \n \f \r、&lt;0x20 → 反斜杠+u+4位小写hex），
 *       非 ASCII（中文等）原样 UTF-8 输出；孤立代理对拒绝；</li>
 *   <li>数字 ECMAScript Number::toString 风格；-0 → "0"；NaN/Infinity 拒绝；
 *       JSON 数字超过 2^53-1 拒绝（bigint 一律以字符串传输）；</li>
 *   <li>输入解析启用 Jackson STRICT_DUPLICATE_DETECTION——重复 JSON 键是
 *       错误而不是覆盖。</li>
 * </ul>
 *
 * <p>数字序列化为标准 ECMAScript {@code Number::toString} 语义
 * （RFC 8785 §4.2.2）：-0 → "0"；|v| &lt; 1e21 的整值 double → 无小数点的
 * 规范十进制；最短往返数字（JDK 19+ 的 {@link Double#toString(double)} 与
 * Python repr 同为最短往返表示，数字序列一致）；n 为小数点相对数字串的
 * 位置，剥离前导零后按 {@code n = intPart.length + exp10 - strippedZeros}
 * 修正（保证 0.5 → "0.5"、0.000123 → "0.000123" 与 jcs.py 逐字节一致）。</p>
 */
public final class Jcs {

    private static final BigInteger MAX_SAFE = BigInteger.valueOf(9007199254740991L);

    /** 严格 ObjectMapper：拒绝重复键、拒绝未知 token 之外的宽松行为。 */
    private static final ObjectMapper STRICT = new ObjectMapper()
            .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    private Jcs() {
    }

    /** 解析 JSON 字符串；重复键/尾随内容/语法错误 → IllegalArgumentException。 */
    public static JsonNode parseStrict(String json) {
        try {
            JsonNode node = STRICT.readTree(json);
            if (node == null) {
                throw new IllegalArgumentException("empty JSON input");
            }
            return node;
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("invalid JSON input: " + e.getOriginalMessage(), e);
        }
    }

    /** 任意 Java 结构（Map/List/String/Integer/Long/Double/Boolean/null）→ JsonNode。 */
    public static JsonNode toNode(Object value) {
        JsonNode node = STRICT.valueToTree(value);
        if (node == null) {
            throw new IllegalArgumentException("value not convertible to JSON");
        }
        return node;
    }

    public static String canonicalize(JsonNode node) {
        StringBuilder sb = new StringBuilder();
        write(node, sb);
        return sb.toString();
    }

    public static byte[] canonicalizeBytes(JsonNode node) {
        return canonicalize(node).getBytes(StandardCharsets.UTF_8);
    }

    /** SHA-256(canonical UTF-8 字节)，小写 hex（无 "sha256:" 前缀；T13 列存裸 hex）。 */
    public static String sha256Hex(JsonNode node) {
        return sha256HexBytes(canonicalizeBytes(node));
    }

    public static String sha256HexBytes(byte[] bytes) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(md.digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    // ---------------- serialization core ----------------

    private static void write(JsonNode n, StringBuilder o) {
        switch (n.getNodeType()) {
            case NULL -> o.append("null");
            case BOOLEAN -> o.append(n.booleanValue() ? "true" : "false");
            case NUMBER -> o.append(numberToString(n));
            case STRING -> appendString(n.textValue(), o);
            case ARRAY -> {
                o.append('[');
                for (int i = 0; i < n.size(); i++) {
                    if (i > 0) o.append(',');
                    write(n.get(i), o);
                }
                o.append(']');
            }
            case OBJECT -> {
                List<String> names = new ArrayList<>();
                n.fieldNames().forEachRemaining(names::add);
                names.sort(String::compareTo); // UTF-16 code-unit order (ES6 sort)
                o.append('{');
                for (int i = 0; i < names.size(); i++) {
                    if (i > 0) o.append(',');
                    appendString(names.get(i), o);
                    o.append(':');
                    write(n.get(names.get(i)), o);
                }
                o.append('}');
            }
            default -> throw new IllegalArgumentException(
                    "unsupported JSON value type: " + n.getNodeType());
        }
    }

    private static void appendString(String s, StringBuilder o) {
        o.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> o.append("\\\"");
                case '\\' -> o.append("\\\\");
                case '\b' -> o.append("\\b");
                case '\t' -> o.append("\\t");
                case '\n' -> o.append("\\n");
                case '\f' -> o.append("\\f");
                case '\r' -> o.append("\\r");
                default -> {
                    if (Character.isHighSurrogate(c)) {
                        if (i + 1 >= s.length() || !Character.isLowSurrogate(s.charAt(i + 1))) {
                            throw new IllegalArgumentException(
                                    "lone surrogate U+" + Integer.toHexString(c) + " in string");
                        }
                        o.append(c).append(s.charAt(++i));
                    } else if (Character.isLowSurrogate(c)) {
                        throw new IllegalArgumentException(
                                "lone surrogate U+" + Integer.toHexString(c) + " in string");
                    } else if (c < 0x20) {
                        o.append("\\u").append(String.format("%04x", (int) c));
                    } else {
                        o.append(c); // 非 ASCII（含中文）原样输出
                    }
                }
            }
        }
        o.append('"');
    }

    /** 与 jcs.py::_number_to_string 一致的标准 ES6 Number::toString（RFC 8785 §4.2.2）。 */
    static String numberToString(JsonNode n) {
        if (n.isIntegralNumber()) {
            BigInteger v = n.bigIntegerValue();
            if (v.abs().compareTo(MAX_SAFE) > 0) {
                throw new IllegalArgumentException(
                        "JSON number exceeds the safe double range; transport big integers as strings");
            }
            return v.toString();
        }
        if (n.isBigDecimal()) {
            // 本项目 JSON 不产生 BigDecimal 数字节点；按 double 规则拒绝越界值
            java.math.BigDecimal bd = n.decimalValue();
            if (bd.abs().compareTo(new java.math.BigDecimal(MAX_SAFE)) > 0) {
                throw new IllegalArgumentException("JSON number exceeds the safe double range");
            }
            return doubleToString(bd.doubleValue());
        }
        if (!n.isFloatingPointNumber()) {
            throw new IllegalArgumentException("unsupported number node: " + n.getNodeType());
        }
        double d = n.doubleValue();
        return doubleToString(d);
    }

    static String doubleToString(double d) {
        if (Double.isNaN(d) || Double.isInfinite(d)) {
            throw new IllegalArgumentException("NaN/Infinity are not serializable per RFC 8785");
        }
        if (d == 0.0) {
            return "0"; // 覆盖 -0
        }
        String sign = d < 0 ? "-" : "";
        double a = Math.abs(d);
        if (a == Math.rint(a) && a < 1e21) {
            return sign + java.math.BigDecimal.valueOf(a).toBigIntegerExact().toString();
        }
        // 最短往返十进制（JDK 19+ Double.toString 与 Python repr 同为最短性+最近值，数字序列一致）
        String s = Double.toString(a);
        int eIdx = s.indexOf('E');
        int exp10 = 0;
        if (eIdx >= 0) {
            exp10 = Integer.parseInt(s.substring(eIdx + 1));
            s = s.substring(0, eIdx);
        }
        int dot = s.indexOf('.');
        String intPart = dot < 0 ? s : s.substring(0, dot);
        String fracPart = dot < 0 ? "" : s.substring(dot + 1);
        String raw = intPart + fracPart;
        String digits = raw.replaceFirst("^0+", "");
        if (digits.isEmpty()) digits = "0";
        // value == 0.raw * 10**(intPart.length()+exp10)；剥 z 个前导零后小数点位置左移 z
        int nPos = intPart.length() + exp10 - (raw.length() - digits.length());
        digits = digits.replaceFirst("0+$", "");
        if (digits.isEmpty()) digits = "0";
        int k = digits.length();
        if (k <= nPos && nPos <= 21) {
            return sign + digits + "0".repeat(nPos - k);
        }
        if (0 < nPos && nPos <= 21) {
            return sign + digits.substring(0, nPos) + "." + digits.substring(nPos);
        }
        if (-6 < nPos && nPos <= 0) {
            return sign + "0." + "0".repeat(-nPos) + digits;
        }
        String m = (k == 1) ? digits : digits.charAt(0) + "." + digits.substring(1);
        int e = nPos - 1;
        return sign + m + (e >= 0 ? "e+" : "e-") + Math.abs(e);
    }

    /** 便捷：从字段顺序无关的 Map 构造 canonical SHA-256。 */
    public static String sha256HexOfObject(Object javaStructure) {
        JsonNode root = toNode(javaStructure);
        if (!root.isObject()) {
            throw new IllegalArgumentException("canonical object must be a JSON object");
        }
        return sha256Hex(root);
    }

    /** 单元测试辅助：返回 canonical ObjectNode（键序无关）。 */
    public static ObjectNode objectNode() {
        return STRICT.createObjectNode();
    }

    public static ArrayNode arrayNode() {
        return STRICT.createArrayNode();
    }
}

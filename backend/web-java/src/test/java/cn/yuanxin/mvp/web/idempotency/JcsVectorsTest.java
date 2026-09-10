package cn.yuanxin.mvp.web.idempotency;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * RFC 8785 JCS：复现 backend/contracts/samples/canonicalization/vectors.json
 * 全部 17 个向量（A/decisions #11；行为基准 scripts/jcs.py，两侧字节一致）。
 * 另测重复键拒绝、-0 归一、越界整数拒绝、ES6 Number::toString 精确对（与
 * `python3 scripts/jcs.py selftest` 同一清单）。
 */
class JcsVectorsTest {

    private static Path vectorsFile() {
        Path direct = Path.of("..", "contracts", "samples", "canonicalization", "vectors.json");
        if (Files.exists(direct)) {
            return direct;
        }
        return Path.of("backend", "contracts", "samples", "canonicalization", "vectors.json");
    }

    static Stream<Arguments> vectors() throws IOException {
        JsonNode arr = Jcs.parseStrict(Files.readString(vectorsFile()));
        assertTrue(arr.isArray() && arr.size() == 17, "契约应提供 17 个向量");
        return StreamSupport.stream(arr.spliterator(), false)
                .map(v -> Arguments.of(v.get("name").asText(), v.get("input"),
                        v.get("expected_sha256").asText()));
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("vectors")
    @DisplayName("向量逐条复现 expected_sha256")
    void reproduceVector(String name, JsonNode input, String expectedSha256) {
        assertEquals(expectedSha256, Jcs.sha256Hex(input), "vector " + name);
    }

    @Test
    void canonicalShapeIsSortedNoWhitespace() {
        JsonNode n = Jcs.parseStrict("{\"b\":1,\"a\":[2,{\"d\":null,\"c\":true}]}");
        assertEquals("{\"a\":[2,{\"c\":true,\"d\":null}],\"b\":1}", Jcs.canonicalize(n));
    }

    @Test
    @DisplayName("重复 JSON 键拒绝（STRICT_DUPLICATE_DETECTION，不是覆盖）")
    void duplicateKeysRejected() {
        assertThrows(IllegalArgumentException.class, () -> Jcs.parseStrict("{\"a\":1,\"a\":2}"));
    }

    @Test
    @DisplayName("-0 → \"0\"；NaN/Infinity/越界 JSON 整数拒绝；bigint 字符串原样")
    void numberEdgeCases() {
        assertEquals("0", Jcs.doubleToString(-0.0));
        assertEquals("0", Jcs.doubleToString(0.0));
        assertThrows(IllegalArgumentException.class, () -> Jcs.doubleToString(Double.NaN));
        assertThrows(IllegalArgumentException.class,
                () -> Jcs.doubleToString(Double.POSITIVE_INFINITY));
        assertThrows(IllegalArgumentException.class,
                () -> Jcs.canonicalize(Jcs.parseStrict("{\"n\":9007199254740993}")));
        assertEquals("{\"n\":\"9007199254740993\"}",
                Jcs.canonicalize(Jcs.parseStrict("{\"n\":\"9007199254740993\"}")));
    }

    static Stream<Arguments> es6NumberPairs() {
        // Same authoritative pairs as jcs.py `_NUMBER_SELFTEST_PAIRS`
        // (`python3 scripts/jcs.py selftest`), ES6 Number::toString exact.
        return Stream.of(
                Arguments.of(0.0, "0"),
                Arguments.of(-0.0, "0"),
                Arguments.of(1.0, "1"),
                Arguments.of(0.5, "0.5"),
                Arguments.of(0.000123, "0.000123"),
                Arguments.of(1e-4, "0.0001"),
                Arguments.of(1e-5, "0.00001"),
                Arguments.of(1e-6, "0.000001"),
                Arguments.of(1e-7, "1e-7"),
                Arguments.of(1e20, "100000000000000000000"),
                Arguments.of(1e21, "1e+21"),
                Arguments.of(1e23, "1e+23"),
                Arguments.of(1e30, "1e+30"),
                Arguments.of(3.14159, "3.14159"),
                Arguments.of(123.456, "123.456"),
                Arguments.of(9007199254740992.0, "9007199254740992"),
                Arguments.of(1.7976931348623157e308, "1.7976931348623157e+308"),
                Arguments.of(2.2250738585072014e-308, "2.2250738585072014e-308"),
                Arguments.of(0.1, "0.1"),
                Arguments.of(-0.5, "-0.5"),
                Arguments.of(1e-3, "0.001"),
                Arguments.of(2.5e-8, "2.5e-8"),
                Arguments.of(1234.5, "1234.5"));
    }

    @ParameterizedTest(name = "{0} -> {1}")
    @MethodSource("es6NumberPairs")
    @DisplayName("ES6 Number::toString 权威数对（与 jcs.py selftest 同清单）")
    void es6NumberToString(double value, String expected) {
        assertEquals(expected, Jcs.doubleToString(value));
    }

    @Test
    @DisplayName("JSON 小数经 numberToString 与 doubleToString 一致（DoubleNode 路径）")
    void numberNodePathMatches() {
        assertEquals("0.5", Jcs.numberToString(Jcs.parseStrict("0.5")));
        assertEquals("0.000123", Jcs.numberToString(Jcs.parseStrict("0.000123")));
        assertEquals("1e+21", Jcs.numberToString(Jcs.parseStrict("1e21")));
        assertEquals("100000000000000000000", Jcs.numberToString(Jcs.parseStrict("1e20")));
        assertEquals("9007199254740992", Jcs.numberToString(Jcs.parseStrict("9007199254740992.0")));
        assertEquals("0", Jcs.numberToString(Jcs.parseStrict("-0.0")));
    }

    @Test
    @DisplayName("孤立代理对拒绝；控制字符最小转义")
    void stringEdgeCases() {
        String lone = "\"" + (char) 0xD800 + "\"";
        assertThrows(IllegalArgumentException.class,
                () -> Jcs.canonicalize(Jcs.parseStrict("{\"k\":" + lone + "}")));
        JsonNode ctrl = Jcs.parseStrict("{\"k\":\"a\\u0001b\"}");
        assertEquals("{\"k\":\"a\\u0001b\"}", Jcs.canonicalize(ctrl));
    }
}

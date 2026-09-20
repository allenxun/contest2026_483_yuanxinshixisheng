package cn.yuanxin.mvp.web.gimbalai;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/** {@link GimbalAiCodes} 归一规则单测（I1）：只放行 {@code ^[A-Z0-9_]{1,64}$}。 */
class GimbalAiCodesTest {

    @Test
    @DisplayName("合法码原样保留；非法码（小写/超长/空格/控制字符/标点/空/null）→ null")
    void sanitizeWhitelist() {
        assertThat(GimbalAiCodes.sanitize("AI_UPSTREAM_TIMEOUT")).isEqualTo("AI_UPSTREAM_TIMEOUT");
        assertThat(GimbalAiCodes.sanitize("A")).isEqualTo("A");
        assertThat(GimbalAiCodes.sanitize("A1_B2")).isEqualTo("A1_B2");
        assertThat(GimbalAiCodes.sanitize("  AI_SERVICE_UNAVAILABLE  "))
                .isEqualTo("AI_SERVICE_UNAVAILABLE");

        for (String invalid : List.of(
                "", " ", "lower_case", "has space and user text", "BAD-CODE", "BAD.CODE",
                "A".repeat(65), "EVIL\nuser", "EVIL\u0001user", "\u4e2d\u6587")) {
            assertThat(GimbalAiCodes.sanitize(invalid)).as("invalid=%s", invalid).isNull();
        }
        assertThat(GimbalAiCodes.sanitize(null)).isNull();
    }

    @Test
    @DisplayName("64 位边界：64 保留、65 拒绝")
    void lengthBoundary() {
        String exactly64 = "A".repeat(64);
        assertThat(GimbalAiCodes.sanitize(exactly64)).isEqualTo(exactly64);
        assertThat(GimbalAiCodes.sanitize("A".repeat(65))).isNull();
    }
}

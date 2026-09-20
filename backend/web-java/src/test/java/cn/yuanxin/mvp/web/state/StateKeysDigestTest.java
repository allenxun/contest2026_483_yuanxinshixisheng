package cn.yuanxin.mvp.web.state;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.security.SecureRandom;
import java.util.Base64;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link StateKeys} 新增的"摘要→键"构造器测试：与既有 token 构造器<b>逐字节一致</b>，
 * 且只接受已归一化的小写 64 位十六进制摘要（绝不接受原文 token，绝不做自动 hash）。
 */
class StateKeysDigestTest {

    private static final SecureRandom RANDOM = new SecureRandom();

    private final StateKeys keys = new StateKeys("b-digest-test:");

    @Test
    @DisplayName("sessionByAccessTokenDigest(sha256Hex(t)) == sessionByAccessToken(t)（随机 token 多次）")
    void accessDigestBuilderIsByteIdenticalToTokenBuilder() {
        for (int i = 0; i < 32; i++) {
            String token = randomToken();
            String digest = StateKeys.sha256Hex(token);
            assertThat(keys.sessionByAccessTokenDigest(digest))
                    .isEqualTo(keys.sessionByAccessToken(token));
            assertThat(keys.sessionByRefreshTokenDigest(digest))
                    .isEqualTo(keys.sessionByRefreshToken(token));
        }
    }

    @Test
    @DisplayName("含前缀且形状正确（sess:at: / sess:rt:）")
    void digestBuildersIncludePrefixAndPurposeSegment() {
        String digest = StateKeys.sha256Hex("some-token");
        assertThat(keys.sessionByAccessTokenDigest(digest)).startsWith("b-digest-test:sess:at:").endsWith(digest);
        assertThat(keys.sessionByRefreshTokenDigest(digest)).startsWith("b-digest-test:sess:rt:").endsWith(digest);
    }

    @Test
    @DisplayName("非法摘要（长度/大写/非 hex/null/空白）一律 IllegalArgumentException，不自动 hash")
    void malformedDigestsRejected() {
        List<String> malformed = List.of(
                "",
                "   ",
                "abc",
                "0".repeat(63),
                "0".repeat(65),
                "A".repeat(64),
                "G".repeat(64),
                "0".repeat(63) + "z",
                "Z" + "0".repeat(63));
        for (String bad : malformed) {
            assertThatThrownBy(() -> keys.sessionByAccessTokenDigest(bad))
                    .as("access digest must reject: '%s'", bad)
                    .isInstanceOf(IllegalArgumentException.class);
            assertThatThrownBy(() -> keys.sessionByRefreshTokenDigest(bad))
                    .as("refresh digest must reject: '%s'", bad)
                    .isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> keys.sessionByAccessTokenDigest(null))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> keys.sessionByRefreshTokenDigest(null))
                .isInstanceOf(IllegalArgumentException.class);
        // 原文 token（URL-safe Base64，43 字符且含非 hex 字符）长度非 64 ⇒ 必须被拒（不会静默双重摘要）。
        String rawToken = randomToken();
        assertThatThrownBy(() -> keys.sessionByAccessTokenDigest(rawToken))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> keys.sessionByRefreshTokenDigest(rawToken))
                .isInstanceOf(IllegalArgumentException.class);
    }

    private static String randomToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }
}

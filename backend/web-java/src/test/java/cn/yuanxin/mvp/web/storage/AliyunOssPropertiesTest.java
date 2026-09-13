package cn.yuanxin.mvp.web.storage;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** {@link AliyunOssProperties} 默认值、缺失键与脱敏单元测试（明显假值）。 */
class AliyunOssPropertiesTest {

    @Test
    @DisplayName("默认值写在代码里；超时下限 1000ms")
    void defaults() {
        AliyunOssProperties props = new AliyunOssProperties(null, null, null, null, null, null, null, null);
        assertThat(props.region()).isEqualTo("cn-hangzhou");
        assertThat(props.endpoint()).isEqualTo("https://oss-cn-hangzhou.aliyuncs.com");
        assertThat(props.bucket()).isNull();
        assertThat(props.connectionTimeoutMillis()).isEqualTo(3000);
        assertThat(props.socketTimeoutMillis()).isEqualTo(3000);

        AliyunOssProperties tiny = new AliyunOssProperties(null, null, "fake-bucket-do-not-use",
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", null, 1, 1);
        assertThat(tiny.connectionTimeoutMillis()).isEqualTo(1000);
        assertThat(tiny.socketTimeoutMillis()).isEqualTo(1000);
    }

    @Test
    @DisplayName("缺失必填键只列键名")
    void missingRequiredKeys() {
        AliyunOssProperties props = new AliyunOssProperties(null, null, "  ", null, "", null, null, null);
        assertThat(props.missingRequiredKeys()).containsExactly(
                "app.storage.oss.bucket",
                "app.storage.oss.access-key-id",
                "app.storage.oss.access-key-secret");
    }

    @Test
    @DisplayName("toString 脱敏：绝不出现 AK/SK/STS")
    void toStringRedactsSecrets() {
        AliyunOssProperties props = new AliyunOssProperties(null, null, "fake-bucket-do-not-use",
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", "FAKE-STS-DO-NOT-USE", null, null);
        String text = props.toString();
        assertThat(text).doesNotContain("LTAI-FAKE-DO-NOT-USE")
                .doesNotContain("FAKE-SECRET-DO-NOT-USE")
                .doesNotContain("FAKE-STS-DO-NOT-USE")
                .contains("<redacted>")
                .contains("fake-bucket-do-not-use");
    }
}

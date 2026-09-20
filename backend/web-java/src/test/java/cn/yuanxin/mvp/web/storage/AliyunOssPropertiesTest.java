package cn.yuanxin.mvp.web.storage;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** {@link AliyunOssProperties} 默认值、缺失键与脱敏单元测试（明显假值）。 */
class AliyunOssPropertiesTest {

    private static final String SERVER_ENDPOINT = "https://oss-fake-server.example.com";
    private static final String PUBLIC_ENDPOINT = "https://oss-fake-public.example.com";

    @Test
    @DisplayName("默认值写在代码里：region 有默认；两个 endpoint 无默认（必填）；超时下限 1000ms")
    void defaults() {
        AliyunOssProperties props = new AliyunOssProperties(
                null, null, null, null, null, null, null, null, null);
        assertThat(props.region()).isEqualTo("cn-hangzhou");
        assertThat(props.serverEndpoint()).isNull();
        assertThat(props.publicEndpoint()).isNull();
        assertThat(props.bucket()).isNull();
        assertThat(props.connectionTimeoutMillis()).isEqualTo(3000);
        assertThat(props.socketTimeoutMillis()).isEqualTo(3000);

        AliyunOssProperties tiny = new AliyunOssProperties(null, null, null, "fake-bucket-do-not-use",
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", null, 1, 1);
        assertThat(tiny.connectionTimeoutMillis()).isEqualTo(1000);
        assertThat(tiny.socketTimeoutMillis()).isEqualTo(1000);
    }

    @Test
    @DisplayName("缺失必填键只列键名（含两个新 endpoint，顺序稳定）")
    void missingRequiredKeys() {
        AliyunOssProperties props = new AliyunOssProperties(
                null, "  ", null, "  ", null, "", null, null, null);
        assertThat(props.missingRequiredKeys()).containsExactly(
                "app.storage.oss.server-endpoint",
                "app.storage.oss.public-endpoint",
                "app.storage.oss.bucket",
                "app.storage.oss.access-key-id",
                "app.storage.oss.access-key-secret");
    }

    @Test
    @DisplayName("toString：两个 endpoint 只报是否已配置（绝不回显取值）；AK/SK/STS 脱敏")
    void toStringRedactsEndpointsAndSecrets() {
        AliyunOssProperties props = new AliyunOssProperties("cn-hangzhou", SERVER_ENDPOINT,
                PUBLIC_ENDPOINT, "fake-bucket-do-not-use",
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", "FAKE-STS-DO-NOT-USE", null, null);
        String text = props.toString();
        assertThat(text)
                .doesNotContain(SERVER_ENDPOINT)
                .doesNotContain(PUBLIC_ENDPOINT)
                .doesNotContain("oss-fake-server.example.com")
                .doesNotContain("oss-fake-public.example.com")
                .doesNotContain("LTAI-FAKE-DO-NOT-USE")
                .doesNotContain("FAKE-SECRET-DO-NOT-USE")
                .doesNotContain("FAKE-STS-DO-NOT-USE")
                .contains("serverEndpoint=<configured>")
                .contains("publicEndpoint=<configured>")
                .contains("<redacted>")
                .contains("fake-bucket-do-not-use");
    }

    @Test
    @DisplayName("toString：endpoint 未配置显示 <absent>（仍不回显取值）")
    void toStringShowsAbsentEndpoints() {
        AliyunOssProperties props = new AliyunOssProperties(
                null, null, null, null, null, null, null, null, null);
        assertThat(props.toString())
                .contains("serverEndpoint=<absent>")
                .contains("publicEndpoint=<absent>");
    }
}

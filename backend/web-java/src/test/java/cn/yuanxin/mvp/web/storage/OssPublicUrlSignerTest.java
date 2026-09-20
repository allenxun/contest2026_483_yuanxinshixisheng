package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.config.AppProperties;
import com.aliyun.oss.OSS;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.env.StandardEnvironment;

import java.net.URI;
import java.net.URL;
import java.time.Duration;
import java.util.Arrays;
import java.util.Date;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * {@link OssPublicUrlSigner} 判别测试：签名必须在**公网 endpoint** 构建的客户端上完成，
 * 返回 URL 原样透传（<b>绝不</b>做 host/scheme 字符串替换）。不访问真实 OSS（签名是本地计算）。
 */
class OssPublicUrlSignerTest {

    private static final String BUCKET = "fake-bucket-do-not-use";
    private static final String KEY = "dev/assessment_result/00000000-0000-4000-8000-000000000000";
    private static final String SERVER_ENDPOINT = "http://127.0.0.1:19001";
    private static final String PUBLIC_ENDPOINT = "http://127.0.0.1:19002";

    @Test
    @DisplayName("签名经注入（公网）客户端，返回 URL 逐字透传，绝不做 host 替换")
    void presignUsesInjectedClientVerbatim() throws Exception {
        OSS publicClient = mock(OSS.class);
        OSS unrelatedServerClient = mock(OSS.class);
        URL publicUrl = URI.create("http://oss-fake-public.example.com/" + BUCKET + "/" + KEY
                + "?Expires=123&Signature=PUB").toURL();
        URL serverUrl = URI.create("http://oss-fake-server.example.com/" + BUCKET + "/" + KEY
                + "?Expires=123&Signature=SERVER").toURL();
        when(publicClient.generatePresignedUrl(eq(BUCKET), eq(KEY), any(Date.class)))
                .thenReturn(publicUrl);
        when(unrelatedServerClient.generatePresignedUrl(anyString(), anyString(), any(Date.class)))
                .thenReturn(serverUrl);

        OssPublicUrlSigner signer = new OssPublicUrlSigner(publicClient, BUCKET);
        URL result = signer.presign(KEY);

        // 逐字等于公网客户端产出（若实现"签名后替换 host"，此处 host 会变 ⇒ 失败）。
        assertThat(result).isEqualTo(publicUrl);
        assertThat(result.getHost()).isEqualTo("oss-fake-public.example.com");
        verify(publicClient).generatePresignedUrl(eq(BUCKET), eq(KEY), any(Date.class));
        verify(unrelatedServerClient, never()).generatePresignedUrl(anyString(), anyString(), any(Date.class));
    }

    @Test
    @DisplayName("装配级：公共端点与服务端点不同时，签名 URL 的 host:port 是公网端点而非服务端端点")
    void presignedUrlTargetsPublicEndpointNotServerEndpoint() {
        AliyunOssProperties props = new AliyunOssProperties("cn-hangzhou",
                SERVER_ENDPOINT, PUBLIC_ENDPOINT, BUCKET,
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", null, 1000, 1000);
        AppProperties appProps = new AppProperties("dev", null,
                new AppProperties.Storage(null, BUCKET), null, null, null, null);
        Environment environment = new StandardEnvironment();
        OssProvidersConfig config = new OssProvidersConfig();
        OSS serverClient = config.ossClient(props, appProps, environment);
        OSS publicClient = config.ossPublicClient(props, environment);
        try {
            OssPublicUrlSigner signer = new OssPublicUrlSigner(publicClient, BUCKET);
            URL url = signer.presign(KEY);
            assertThat(url.getHost()).isEqualTo("127.0.0.1");
            assertThat(url.getPort()).as("必须是公网端点端口").isEqualTo(19002);
            assertThat(url.getPort()).as("绝不能是服务端端点端口").isNotEqualTo(19001);
            assertThat(signer.presignedHost(KEY)).isEqualTo("127.0.0.1");
        } finally {
            // 两个客户端都必须能 shutdown（生命周期，防泄漏）。
            serverClient.shutdown();
            publicClient.shutdown();
        }
    }

    @Test
    @DisplayName("TTL 超上限（>7 天）明确失败，不静默截断")
    void ttlAboveMaximumIsRejected() {
        OSS publicClient = mock(OSS.class);
        OssPublicUrlSigner signer = new OssPublicUrlSigner(publicClient, BUCKET);
        assertThatThrownBy(() -> signer.presign(KEY, Duration.ofDays(8)))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("604800");
        verify(publicClient, never()).generatePresignedUrl(anyString(), anyString(), any(Date.class));
    }

    @Test
    @DisplayName("TTL 为 null/零/负数/亚秒 ⇒ 明确失败，绝不静默回退默认值（与 Python 侧 1..604800 一致）")
    void nonPositiveTtlIsRejectedNotSilentlyDefaulted() {
        OSS publicClient = mock(OSS.class);
        OssPublicUrlSigner signer = new OssPublicUrlSigner(publicClient, BUCKET);
        // 亚秒级 TTL 必须拒绝：Duration.ofNanos(1).toMillis() == 0 ⇒ 会生成**立即过期**的 URL。
        for (Duration bad : Arrays.asList(null, Duration.ZERO, Duration.ofSeconds(-1),
                Duration.ofNanos(1), Duration.ofMillis(500), Duration.ofMillis(999))) {
            assertThatThrownBy(() -> signer.presign(KEY, bad))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("positive");
        }
        // 全部非法 TTL 都不得触发任何签名调用（失败必须早于签名）。
        verify(publicClient, never()).generatePresignedUrl(anyString(), anyString(), any(Date.class));
        // 单参入口是"调用方显式选择默认值"，不属于静默替换：它不应抛异常。
        signer.presign(KEY);
    }

    @Test
    @DisplayName("TTL 边界：1 秒可接受（下界），恰 7 天可接受（上界），7 天 + 1 秒拒绝")
    void ttlBoundariesAreExact() {
        OSS publicClient = mock(OSS.class);
        when(publicClient.generatePresignedUrl(anyString(), anyString(), any(Date.class)))
                .thenReturn(null);
        OssPublicUrlSigner signer = new OssPublicUrlSigner(publicClient, BUCKET);
        // 下界与上界都不得抛异常。
        signer.presign(KEY, OssPublicUrlSigner.MIN_EXPIRY);
        signer.presign(KEY, OssPublicUrlSigner.MAX_EXPIRY);
        // 上界 + 1 秒必须拒绝，且失败早于签名调用。
        assertThatThrownBy(() -> signer.presign(KEY, OssPublicUrlSigner.MAX_EXPIRY.plusSeconds(1)))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("604800");
        verify(publicClient, times(2)).generatePresignedUrl(anyString(), anyString(), any(Date.class));
    }

    @Test
    @DisplayName("生命周期：两个 OSS @Bean 均声明 destroyMethod=shutdown")
    void bothOssBeansDeclareShutdown() throws Exception {
        Bean serverBean = OssProvidersConfig.class
                .getMethod("ossClient", AliyunOssProperties.class, AppProperties.class, Environment.class)
                .getAnnotation(Bean.class);
        Bean publicBean = OssProvidersConfig.class
                .getMethod("ossPublicClient", AliyunOssProperties.class, Environment.class)
                .getAnnotation(Bean.class);
        assertThat(serverBean.destroyMethod()).isEqualTo("shutdown");
        assertThat(publicBean.destroyMethod()).isEqualTo("shutdown");
    }
}

package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.config.DisabledProvidersConfig;
import cn.yuanxin.mvp.web.config.ProvidersModeProductionGuard;
import cn.yuanxin.mvp.web.config.TestDoubleProvidersConfig;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * 存储装配矩阵（{@link ApplicationContextRunner}，不启动 web/PG、不访问真实 OSS）。
 * 优先级：{@code app.providers.mode=disabled} &gt; {@code app.storage.provider=aliyun} &gt; 默认 doubles。
 * 双 endpoint 语义：{@code server-endpoint} 必填且用于对象操作；{@code public-endpoint} 必填且
 * 用于签名地址；旧 {@code app.storage.oss.endpoint} 不再支持。
 */
class OssProvidersConfigTest {

    private static final String BUCKET = "fake-bucket-do-not-use";
    private static final String SERVER_ENDPOINT = "https://oss-fake-server.example.com";
    private static final String PUBLIC_ENDPOINT = "https://oss-fake-public.example.com";

    @Configuration
    @EnableConfigurationProperties({AppProperties.class, AliyunOssProperties.class})
    static class PropsConfig {
    }

    @Configuration
    static class JdbcConfig {
        @Bean
        JdbcTemplate jdbcTemplate() {
            return org.mockito.Mockito.mock(JdbcTemplate.class);
        }
    }

    private static ApplicationContextRunner runner(String... profiles) {
        return new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class, DisabledProvidersConfig.class,
                        OssProvidersConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles(profiles));
    }

    private static String[] fakeAliyun() {
        return new String[]{
                "app.storage.provider=aliyun",
                "app.storage.bucket=" + BUCKET,
                "app.storage.oss.bucket=" + BUCKET,
                "app.storage.oss.access-key-id=LTAI-FAKE-DO-NOT-USE",
                "app.storage.oss.access-key-secret=FAKE-SECRET-DO-NOT-USE",
                "app.storage.oss.server-endpoint=" + SERVER_ENDPOINT,
                "app.storage.oss.public-endpoint=" + PUBLIC_ENDPOINT};
    }

    @Test
    @DisplayName("mode=doubles + provider 缺省 → FileSystemStorageDouble（失败注入仍生效）")
    void defaultDoubles() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.storage.dev-dir=target/storage-it/oss-config",
                        "APP_DOUBLE_STORAGE_FAIL_MODE=fail-put:assessment_source")
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    StoragePort bean = ctx.getBean(StoragePort.class);
                    assertThat(bean).isInstanceOf(FileSystemStorageDouble.class);
                    assertThat(((FileSystemStorageDouble) bean).failPurposes())
                            .containsExactly("assessment_source");
                });
    }

    @Test
    @DisplayName("mode=doubles + provider=aliyun → OssStorageAdapter（非 doubles），且两个 OSS 客户端 + 签名器均装配")
    void aliyunAdapterAssembled() {
        runner("local").withPropertyValues("app.env=dev").withPropertyValues(fakeAliyun())
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBean(StoragePort.class)).isInstanceOf(OssStorageAdapter.class);
                    assertThat(ctx).hasBean("ossClient");
                    assertThat(ctx).hasBean("ossPublicClient");
                    assertThat(ctx.getBean(OssPublicUrlSigner.class)).isNotNull();
                });
    }

    @Test
    @DisplayName("装配级：签名器 bean 的签名 URL 指向 public-endpoint 而非 server-endpoint")
    void signerBeanTargetsPublicEndpoint() {
        runner("local").withPropertyValues("app.env=dev").withPropertyValues(fakeAliyun())
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    OssPublicUrlSigner signer = ctx.getBean(OssPublicUrlSigner.class);
                    java.net.URL url = signer.presign(
                            "dev/assessment_result/00000000-0000-4000-8000-000000000000");
                    // virtual-host 形态：<bucket>.<public-host>；关键是落在 public 域而非 server 域。
                    assertThat(url.getHost()).endsWith("oss-fake-public.example.com");
                    assertThat(url.getHost()).doesNotContain("oss-fake-server.example.com");
                });
    }

    @Test
    @DisplayName("mode=disabled + provider=aliyun → disabled 占位 503（aliyun 不装配）")
    void disabledWinsOverAliyun() {
        runner("local").withPropertyValues("app.env=dev", "app.providers.mode=disabled")
                .withPropertyValues(fakeAliyun())
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    StoragePort bean = ctx.getBean(StoragePort.class);
                    assertThat(bean).isNotInstanceOf(OssStorageAdapter.class)
                            .isNotInstanceOf(FileSystemStorageDouble.class);
                    ApiException failure = assertThrows(ApiException.class,
                            () -> bean.put("dev/assessment_source/x",
                                    new ByteArrayInputStream("x".getBytes(StandardCharsets.UTF_8)),
                                    1, "image/png"));
                    assertThat(failure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
                    assertThat(failure.getHttpStatus()).isEqualTo(503);
                });
    }

    @Test
    @DisplayName("provider=aliyun 缺必填键 → 拒绝启动且只列键名（不回显值）")
    void missingKeysRefuseStartup() {
        runner("local").withPropertyValues("app.env=dev", "app.storage.provider=aliyun")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("app.storage.oss.server-endpoint")
                            .hasMessageContaining("app.storage.oss.public-endpoint")
                            .hasMessageContaining("app.storage.oss.bucket")
                            .hasMessageContaining("app.storage.oss.access-key-id")
                            .hasMessageContaining("values are never logged")
                            .hasMessageNotContaining("FAKE-SECRET-DO-NOT-USE");
                });
    }

    @Test
    @DisplayName("缺 server-endpoint ⇒ 拒绝启动、消息点名该键、不含任何 endpoint 取值")
    void missingServerEndpointRefusesStartup() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.storage.provider=aliyun",
                        "app.storage.bucket=" + BUCKET,
                        "app.storage.oss.bucket=" + BUCKET,
                        "app.storage.oss.access-key-id=LTAI-FAKE-DO-NOT-USE",
                        "app.storage.oss.access-key-secret=FAKE-SECRET-DO-NOT-USE",
                        "app.storage.oss.public-endpoint=" + PUBLIC_ENDPOINT)
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("app.storage.oss.server-endpoint")
                            .hasMessageNotContaining(PUBLIC_ENDPOINT)
                            .hasMessageNotContaining("oss-fake-public.example.com")
                            .hasMessageNotContaining("FAKE-SECRET-DO-NOT-USE");
                });
    }

    @Test
    @DisplayName("缺 public-endpoint ⇒ 拒绝启动、消息点名该键、不含任何 endpoint 取值")
    void missingPublicEndpointRefusesStartup() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.storage.provider=aliyun",
                        "app.storage.bucket=" + BUCKET,
                        "app.storage.oss.bucket=" + BUCKET,
                        "app.storage.oss.access-key-id=LTAI-FAKE-DO-NOT-USE",
                        "app.storage.oss.access-key-secret=FAKE-SECRET-DO-NOT-USE",
                        "app.storage.oss.server-endpoint=" + SERVER_ENDPOINT)
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("app.storage.oss.public-endpoint")
                            .hasMessageNotContaining(SERVER_ENDPOINT)
                            .hasMessageNotContaining("oss-fake-server.example.com")
                            .hasMessageNotContaining("FAKE-SECRET-DO-NOT-USE");
                });
    }

    @Test
    @DisplayName("只配旧 app.storage.oss.endpoint ⇒ 拒绝启动 + 迁移提示（点名两个新键，不回显取值）")
    void legacyEndpointOnlyRefusesStartupWithMigrationHint() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.storage.provider=aliyun",
                        "app.storage.bucket=" + BUCKET,
                        "app.storage.oss.bucket=" + BUCKET,
                        "app.storage.oss.access-key-id=LTAI-FAKE-DO-NOT-USE",
                        "app.storage.oss.access-key-secret=FAKE-SECRET-DO-NOT-USE",
                        "app.storage.oss.endpoint=https://legacy-endpoint.example.com")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class)
                            .hasMessageContaining("legacy app.storage.oss.endpoint is no longer supported")
                            .hasMessageContaining("app.storage.oss.server-endpoint")
                            .hasMessageContaining("app.storage.oss.public-endpoint")
                            .hasMessageNotContaining("legacy-endpoint.example.com")
                            .hasMessageNotContaining("FAKE-SECRET-DO-NOT-USE");
                });
    }

    @Test
    @DisplayName("两个新键齐备时旧 endpoint 存在也被完全忽略（正常装配）")
    void legacyEndpointIgnoredWhenNewKeysPresent() {
        runner("local").withPropertyValues("app.env=dev", "app.storage.oss.endpoint=https://legacy-endpoint.example.com")
                .withPropertyValues(fakeAliyun())
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBean(StoragePort.class)).isInstanceOf(OssStorageAdapter.class);
                });
    }

    @Test
    @DisplayName("bucket 不一致（app.storage.oss.bucket != app.storage.bucket）→ 拒绝启动，且不回显桶名")
    void bucketMismatchRefusesStartup() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.storage.provider=aliyun",
                        "app.storage.bucket=other-bucket",
                        "app.storage.oss.bucket=" + BUCKET,
                        "app.storage.oss.access-key-id=LTAI-FAKE-DO-NOT-USE",
                        "app.storage.oss.access-key-secret=FAKE-SECRET-DO-NOT-USE",
                        "app.storage.oss.server-endpoint=" + SERVER_ENDPOINT,
                        "app.storage.oss.public-endpoint=" + PUBLIC_ENDPOINT)
                .run(ctx -> {
                    // "启动被拒"断言不得弱化。
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class)
                            .hasMessageContaining("bucket mismatch")
                            .hasMessageContaining("app.storage.oss.bucket")
                            .hasMessageContaining("app.storage.bucket")
                            .hasMessageContaining("values omitted")
                            // 日志卫生：绝不含任一侧真实桶名取值。
                            .hasMessageNotContaining(BUCKET)
                            .hasMessageNotContaining("other-bucket")
                            .hasMessageNotContaining("FAKE-SECRET-DO-NOT-USE");
                });
    }

    @Test
    @DisplayName("生产信号 + mode=doubles（provider 任意）→ 既有早期守卫仍拒绝，未被本轮绕过")
    void productionSignalStillRejected() {
        new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, JdbcConfig.class,
                        TestDoubleProvidersConfig.class, DisabledProvidersConfig.class,
                        OssProvidersConfig.class, ProvidersModeProductionGuard.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles("prod"))
                .withPropertyValues("app.env=dev", "app.providers.mode=doubles")
                .withPropertyValues(fakeAliyun())
                .run(ctx -> assertThat(ctx).hasFailed()
                        .getFailure()
                        .isInstanceOf(IllegalStateException.class)
                        .hasMessageContaining("app.providers.mode=doubles is not allowed"));
    }
}

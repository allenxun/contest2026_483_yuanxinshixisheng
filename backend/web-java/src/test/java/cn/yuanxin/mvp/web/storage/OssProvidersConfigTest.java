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
 */
class OssProvidersConfigTest {

    private static final String BUCKET = "fake-bucket-do-not-use";

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
                "app.storage.oss.endpoint=https://oss-cn-hangzhou.aliyuncs.com"};
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
    @DisplayName("mode=doubles + provider=aliyun → OssStorageAdapter（非 doubles）")
    void aliyunAdapterAssembled() {
        runner("local").withPropertyValues("app.env=dev").withPropertyValues(fakeAliyun())
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx.getBean(StoragePort.class)).isInstanceOf(OssStorageAdapter.class);
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
                            .hasMessageContaining("app.storage.oss.bucket")
                            .hasMessageContaining("app.storage.oss.access-key-id")
                            .hasMessageContaining("values are never logged")
                            .hasMessageNotContaining("FAKE-SECRET-DO-NOT-USE");
                });
    }

    @Test
    @DisplayName("bucket 不一致（app.storage.oss.bucket != app.storage.bucket）→ 拒绝启动")
    void bucketMismatchRefusesStartup() {
        runner("local").withPropertyValues("app.env=dev",
                        "app.storage.provider=aliyun",
                        "app.storage.bucket=other-bucket",
                        "app.storage.oss.bucket=" + BUCKET,
                        "app.storage.oss.access-key-id=LTAI-FAKE-DO-NOT-USE",
                        "app.storage.oss.access-key-secret=FAKE-SECRET-DO-NOT-USE")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("bucket mismatch")
                            .hasMessageContaining("other-bucket")
                            .hasMessageContaining(BUCKET)
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

package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.media.StoragePort;
import com.aliyun.oss.ClientBuilderConfiguration;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.common.auth.DefaultCredentialProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import java.util.List;
import java.util.Objects;

/**
 * 真实阿里云 OSS 装配（B 自有）：仅当 {@code app.storage.provider=aliyun} <b>且</b>
 * {@code app.providers.mode != disabled}（{@link StorageProviderEnabledCondition}）时装配
 * {@link OssStorageAdapter}、签名器与两个 {@link OSS} 客户端（容器关闭时均 {@code shutdown()}）。
 *
 * <p><b>两个 endpoint 的分工</b>：</p>
 * <ul>
 *   <li><b>服务端 endpoint</b> {@code app.storage.oss.server-endpoint} → 对象操作客户端
 *       {@link #ossClient}，{@link OssStorageAdapter} 的 put/get/exists/delete 全部用它；</li>
 *   <li><b>公网 endpoint</b> {@code app.storage.oss.public-endpoint} → 独立签名客户端
 *       {@link #ossPublicClient}，仅供 {@link OssPublicUrlSigner} 调用 {@code generatePresignedUrl}。
 *       <b>绝不</b>对签名 URL 做 host 替换。</li>
 * </ul>
 *
 * <p><b>优先级</b>：{@code app.providers.mode=disabled} 高于 {@code app.storage.provider}
 * ——能力显式关闭时存储走 A 的 disabled 占位（503），真实适配器不装配。</p>
 *
 * <p><b>启动期校验（只报键名/不回显取值）</b>：</p>
 * <ol>
 *   <li>缺 {@code server-endpoint}/{@code public-endpoint}/{@code bucket}/
 *       {@code access-key-id}/{@code access-key-secret} 任一 ⇒ 拒绝启动，列出缺失<b>键名</b>；</li>
 *   <li>只配旧的 {@code app.storage.oss.endpoint} ⇒ 拒绝启动并给出迁移提示
 *       （点名两个新键）。旧键<b>绝不</b>被读取/回退；两个新键齐备时旧键被完全忽略；</li>
 *   <li><b>bucket 一致性</b>：{@code app.storage.oss.bucket} 必须等于 {@code app.storage.bucket}
 *       ——因为 {@code MediaService} 把 {@code media_objects.bucket} 写成 {@code app.storage.bucket}
 *       （A 侧写入，B 不得改），而真实对象写在 {@code app.storage.oss.bucket}。两者不一致 ⇒
 *       拒绝启动（消息只说明哪两个<b>键名</b>不一致并标注 {@code values omitted}，
 *       <b>绝不</b>回显任何 bucket 名、endpoint、AK/SK/token）。</li>
 * </ol>
 *
 * <p>新类位于 {@code cn.yuanxin.mvp.web.storage} 且类名不以 {@code Disabled} 开头 ⇒
 * {@code ProductionFailClosedValidator.isDouble()} 不会把 {@link OssStorageAdapter} 误判为替身。</p>
 */
@Configuration
@ConditionalOnProperty(name = "app.storage.provider", havingValue = "aliyun")
@Conditional(StorageProviderEnabledCondition.class)
@EnableConfigurationProperties(AliyunOssProperties.class)
public class OssProvidersConfig {

    /** 旧单 endpoint 键：不再支持，仅用于检测并给出迁移提示（绝不读取其值）。 */
    static final String LEGACY_ENDPOINT_KEY = "app.storage.oss.endpoint";
    static final String LEGACY_ENDPOINT_ENV = "APP_STORAGE_OSS_ENDPOINT";

    /** 服务端对象操作客户端（由 {@code server-endpoint} 构建）。 */
    @Bean(destroyMethod = "shutdown")
    public OSS ossClient(AliyunOssProperties properties, AppProperties appProperties,
                         Environment environment) {
        validateEndpointConfig(properties, environment);
        if (!Objects.equals(properties.bucket(), appProperties.storage().bucket())) {
            // 日志卫生：只暴露"哪两个键不一致"，绝不回显 bucket 名取值。
            throw new IllegalStateException("app.storage.provider=aliyun bucket mismatch:"
                    + " app.storage.oss.bucket != app.storage.bucket (values omitted);"
                    + " media_objects.bucket is written from app.storage.bucket, so both must match");
        }
        return buildClient(properties, properties.serverEndpoint());
    }

    /** 独立签名客户端（由 {@code public-endpoint} 构建）；生命周期与对象客户端分开且都关闭。 */
    @Bean(destroyMethod = "shutdown")
    public OSS ossPublicClient(AliyunOssProperties properties, Environment environment) {
        validateEndpointConfig(properties, environment);
        return buildClient(properties, properties.publicEndpoint());
    }

    @Bean
    public StoragePort ossStorageAdapter(@Qualifier("ossClient") OSS ossClient,
                                         AliyunOssProperties properties) {
        return new OssStorageAdapter(ossClient, properties.bucket());
    }

    @Bean
    public OssPublicUrlSigner ossPublicUrlSigner(
            @Qualifier("ossPublicClient") OSS ossPublicClient, AliyunOssProperties properties) {
        return new OssPublicUrlSigner(ossPublicClient, properties.bucket());
    }

    /** 缺键 + 旧键迁移提示；消息只含键名，绝不回显任何取值。 */
    static void validateEndpointConfig(AliyunOssProperties properties, Environment environment) {
        List<String> missing = properties.missingRequiredKeys();
        boolean endpointMissing = missing.contains(AliyunOssProperties.SERVER_ENDPOINT_KEY)
                || missing.contains(AliyunOssProperties.PUBLIC_ENDPOINT_KEY);
        if (endpointMissing && legacyEndpointConfigured(environment)) {
            throw new IllegalStateException("legacy " + LEGACY_ENDPOINT_KEY
                    + " is no longer supported; configure "
                    + AliyunOssProperties.SERVER_ENDPOINT_KEY + " and "
                    + AliyunOssProperties.PUBLIC_ENDPOINT_KEY + " (values are never logged)");
        }
        if (!missing.isEmpty()) {
            throw new IllegalStateException("app.storage.provider=aliyun missing required config keys: "
                    + missing + " (values are never logged)");
        }
    }

    /** 只检测旧键是否<b>存在</b>（yaml 键或环境变量 relaxed 名），绝不读取其值。 */
    private static boolean legacyEndpointConfigured(Environment environment) {
        return environment != null && (environment.containsProperty(LEGACY_ENDPOINT_KEY)
                || environment.containsProperty(LEGACY_ENDPOINT_ENV));
    }

    private static OSS buildClient(AliyunOssProperties properties, String endpoint) {
        ClientBuilderConfiguration clientConfiguration = new ClientBuilderConfiguration();
        clientConfiguration.setConnectionTimeout(properties.connectionTimeoutMillis());
        clientConfiguration.setSocketTimeout(properties.socketTimeoutMillis());
        DefaultCredentialProvider credentials = properties.securityToken() == null
                ? new DefaultCredentialProvider(properties.accessKeyId(), properties.accessKeySecret())
                : new DefaultCredentialProvider(properties.accessKeyId(), properties.accessKeySecret(),
                        properties.securityToken());
        return OSSClientBuilder.create()
                .endpoint(endpoint)
                .region(properties.region())
                .credentialsProvider(credentials)
                .clientConfiguration(clientConfiguration)
                .build();
    }
}

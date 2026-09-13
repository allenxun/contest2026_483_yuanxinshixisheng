package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.media.StoragePort;
import com.aliyun.oss.ClientBuilderConfiguration;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.common.auth.DefaultCredentialProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

import java.util.List;
import java.util.Objects;

/**
 * 真实阿里云 OSS 装配（B 自有）：仅当 {@code app.storage.provider=aliyun} <b>且</b>
 * {@code app.providers.mode != disabled}（{@link StorageProviderEnabledCondition}）时装配
 * {@link OssStorageAdapter} 与单例 {@link OSS} 客户端（容器关闭时 {@code shutdown()}）。
 *
 * <p><b>优先级</b>：{@code app.providers.mode=disabled} 高于 {@code app.storage.provider}
 * ——能力显式关闭时存储走 A 的 disabled 占位（503），真实适配器不装配。</p>
 *
 * <p><b>启动期校验</b>：</p>
 * <ol>
 *   <li>{@code provider=aliyun} 缺 {@code bucket}/{@code access-key-id}/{@code access-key-secret}
 *       任一 ⇒ 拒绝启动，消息只列缺失<b>键名</b>；</li>
 *   <li><b>bucket 一致性</b>：{@code app.storage.oss.bucket} 必须等于 {@code app.storage.bucket}
 *       ——因为 {@code MediaService} 把 {@code media_objects.bucket} 写成 {@code app.storage.bucket}
 *       （A 侧写入，B 不得改），而真实对象写在 {@code app.storage.oss.bucket}。两者不一致 ⇒
 *       拒绝启动（消息可输出 bucket 名，不输出 AK/SK/token）。</li>
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

    @Bean(destroyMethod = "shutdown")
    public OSS ossClient(AliyunOssProperties properties, AppProperties appProperties) {
        List<String> missing = properties.missingRequiredKeys();
        if (!missing.isEmpty()) {
            throw new IllegalStateException("app.storage.provider=aliyun missing required config keys: "
                    + missing + " (values are never logged)");
        }
        if (!Objects.equals(properties.bucket(), appProperties.storage().bucket())) {
            throw new IllegalStateException("app.storage.provider=aliyun bucket mismatch:"
                    + " app.storage.oss.bucket=" + properties.bucket()
                    + " != app.storage.bucket=" + appProperties.storage().bucket()
                    + "; media_objects.bucket is written from app.storage.bucket, so both must match");
        }
        ClientBuilderConfiguration clientConfiguration = new ClientBuilderConfiguration();
        clientConfiguration.setConnectionTimeout(properties.connectionTimeoutMillis());
        clientConfiguration.setSocketTimeout(properties.socketTimeoutMillis());
        DefaultCredentialProvider credentials = properties.securityToken() == null
                ? new DefaultCredentialProvider(properties.accessKeyId(), properties.accessKeySecret())
                : new DefaultCredentialProvider(properties.accessKeyId(), properties.accessKeySecret(),
                        properties.securityToken());
        return OSSClientBuilder.create()
                .endpoint(properties.endpoint())
                .region(properties.region())
                .credentialsProvider(credentials)
                .clientConfiguration(clientConfiguration)
                .build();
    }

    @Bean
    public StoragePort ossStorageAdapter(OSS ossClient, AliyunOssProperties properties) {
        return new OssStorageAdapter(ossClient, properties.bucket());
    }
}

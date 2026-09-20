package cn.yuanxin.mvp.web.storage;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.ArrayList;
import java.util.List;

/**
 * 阿里云 OSS 配置（{@code app.storage.oss.*}）。<b>默认值全部写在代码里</b>
 * （不写 application.yml）。compact constructor 做 trim、空值归一与默认值填充。
 *
 * <p><b>两个 endpoint（两者都必填、都没有默认值）</b>：</p>
 * <ul>
 *   <li>{@code server-endpoint}：服务端访问地址，所有对象操作（put/get/exists/delete）使用；</li>
 *   <li>{@code public-endpoint}：客户端公网地址，仅用于生成签名地址（{@link OssPublicUrlSigner}）。</li>
 * </ul>
 * <p>旧的单一 {@code app.storage.oss.endpoint} <b>不再支持</b>：本类型不声明该组件、无默认值、
 * 无 fallback（旧键被 {@link OssProvidersConfig} 显式拒绝并给出迁移提示）。</p>
 *
 * <p><b>安全：</b>缺失校验只输出<b>键名</b>（{@link #missingRequiredKeys()}），绝不回显
 * endpoint / AccessKeySecret / SecurityToken 等值；{@link #toString()} 对两个 endpoint 只输出
 * 是否已配置，AK/SK/STS 一律脱敏。</p>
 *
 * <p>超时默认 3000ms；传入非正值会被夹到 1000ms（保守下限）。</p>
 */
@ConfigurationProperties(prefix = "app.storage.oss")
public record AliyunOssProperties(
        String region,
        String serverEndpoint,
        String publicEndpoint,
        String bucket,
        String accessKeyId,
        String accessKeySecret,
        String securityToken,
        Integer connectionTimeoutMillis,
        Integer socketTimeoutMillis) {

    public static final String DEFAULT_REGION = "cn-hangzhou";
    public static final String SERVER_ENDPOINT_KEY = "app.storage.oss.server-endpoint";
    public static final String PUBLIC_ENDPOINT_KEY = "app.storage.oss.public-endpoint";
    public static final int DEFAULT_CONNECTION_TIMEOUT_MILLIS = 3000;
    public static final int DEFAULT_SOCKET_TIMEOUT_MILLIS = 3000;
    public static final int MIN_TIMEOUT_MILLIS = 1000;

    public AliyunOssProperties {
        region = defaultIfBlank(region, DEFAULT_REGION);
        serverEndpoint = trimToNull(serverEndpoint);
        publicEndpoint = trimToNull(publicEndpoint);
        bucket = trimToNull(bucket);
        accessKeyId = trimToNull(accessKeyId);
        accessKeySecret = trimToNull(accessKeySecret);
        securityToken = trimToNull(securityToken);
        connectionTimeoutMillis = normalizeTimeout(connectionTimeoutMillis,
                DEFAULT_CONNECTION_TIMEOUT_MILLIS);
        socketTimeoutMillis = normalizeTimeout(socketTimeoutMillis, DEFAULT_SOCKET_TIMEOUT_MILLIS);
    }

    /** 缺失的必填键（仅键名；顺序稳定）。空列表表示配置完整。 */
    public List<String> missingRequiredKeys() {
        List<String> missing = new ArrayList<>();
        if (serverEndpoint == null) {
            missing.add(SERVER_ENDPOINT_KEY);
        }
        if (publicEndpoint == null) {
            missing.add(PUBLIC_ENDPOINT_KEY);
        }
        if (bucket == null) {
            missing.add("app.storage.oss.bucket");
        }
        if (accessKeyId == null) {
            missing.add("app.storage.oss.access-key-id");
        }
        if (accessKeySecret == null) {
            missing.add("app.storage.oss.access-key-secret");
        }
        return missing;
    }

    /** 覆盖 record 自动 toString：endpoint 只报是否配置；AK/SK/STS 脱敏。 */
    @Override
    public String toString() {
        return "AliyunOssProperties[region=" + region
                + ", serverEndpoint=" + configured(serverEndpoint)
                + ", publicEndpoint=" + configured(publicEndpoint)
                + ", bucket=" + bucket
                + ", accessKeyId=" + redacted(accessKeyId)
                + ", accessKeySecret=" + redacted(accessKeySecret)
                + ", securityToken=" + redacted(securityToken)
                + ", connectionTimeoutMillis=" + connectionTimeoutMillis
                + ", socketTimeoutMillis=" + socketTimeoutMillis + "]";
    }

    private static String redacted(String value) {
        return value == null ? "<absent>" : "<redacted>";
    }

    private static String configured(String value) {
        return value == null ? "<absent>" : "<configured>";
    }

    private static Integer normalizeTimeout(Integer value, int fallback) {
        int normalized = value == null || value <= 0 ? fallback : value;
        return Math.max(MIN_TIMEOUT_MILLIS, normalized);
    }

    private static String defaultIfBlank(String value, String fallback) {
        String trimmed = trimToNull(value);
        return trimmed == null ? fallback : trimmed;
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}

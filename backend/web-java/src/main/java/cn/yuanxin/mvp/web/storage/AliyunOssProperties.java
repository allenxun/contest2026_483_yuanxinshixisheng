package cn.yuanxin.mvp.web.storage;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.ArrayList;
import java.util.List;

/**
 * 阿里云 OSS 配置（{@code app.storage.oss.*}）。<b>默认值全部写在代码里</b>
 * （不写 application.yml）。compact constructor 做 trim、空值归一与默认值填充。
 *
 * <p><b>安全：</b>缺失校验只输出<b>键名</b>（{@link #missingRequiredKeys()}），绝不回显
 * AccessKeySecret / SecurityToken 等值；{@link #toString()} 已脱敏。</p>
 *
 * <p>超时默认 3000ms；传入非正值会被夹到 1000ms（保守下限）。</p>
 */
@ConfigurationProperties(prefix = "app.storage.oss")
public record AliyunOssProperties(
        String region,
        String endpoint,
        String bucket,
        String accessKeyId,
        String accessKeySecret,
        String securityToken,
        Integer connectionTimeoutMillis,
        Integer socketTimeoutMillis) {

    public static final String DEFAULT_REGION = "cn-hangzhou";
    public static final String DEFAULT_ENDPOINT = "https://oss-cn-hangzhou.aliyuncs.com";
    public static final int DEFAULT_CONNECTION_TIMEOUT_MILLIS = 3000;
    public static final int DEFAULT_SOCKET_TIMEOUT_MILLIS = 3000;
    public static final int MIN_TIMEOUT_MILLIS = 1000;

    public AliyunOssProperties {
        region = defaultIfBlank(region, DEFAULT_REGION);
        endpoint = defaultIfBlank(endpoint, DEFAULT_ENDPOINT);
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

    /** 覆盖 record 自动 toString：绝不泄露凭据值（AccessKey/Secret/STS）。 */
    @Override
    public String toString() {
        return "AliyunOssProperties[region=" + region + ", endpoint=" + endpoint
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

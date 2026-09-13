package cn.yuanxin.mvp.web.sms;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.ArrayList;
import java.util.List;

/**
 * 阿里云短信 V2.0 配置（{@code app.sms.aliyun.*}）。<b>默认值全部写在代码里</b>
 * （不写 application.yml）。compact constructor 做 trim、空值归一与默认值填充。
 *
 * <p><b>安全：</b>本类不记录、不 toString 任何凭据值；缺失校验只输出<b>键名</b>
 * （{@link #missingRequiredKeys()}），绝不回显 AccessKeySecret / SecurityToken 等值。</p>
 *
 * <p>超时默认 3000ms（官方建议不低于 1 秒）；传入非正值会被夹到 1000ms。</p>
 */
@ConfigurationProperties(prefix = "app.sms.aliyun")
public record AliyunSmsProperties(
        String endpoint,
        String regionId,
        String accessKeyId,
        String accessKeySecret,
        String securityToken,
        String signName,
        String templateCode,
        String templateParamName,
        Integer connectTimeoutMillis,
        Integer readTimeoutMillis) {

    public static final String DEFAULT_ENDPOINT = "dysmsapi.aliyuncs.com";
    public static final String DEFAULT_REGION = "cn-hangzhou";
    public static final String DEFAULT_TEMPLATE_PARAM = "code";
    public static final int DEFAULT_CONNECT_TIMEOUT_MILLIS = 3000;
    public static final int DEFAULT_READ_TIMEOUT_MILLIS = 3000;
    public static final int MIN_TIMEOUT_MILLIS = 1000;

    public AliyunSmsProperties {
        endpoint = defaultIfBlank(endpoint, DEFAULT_ENDPOINT);
        regionId = defaultIfBlank(regionId, DEFAULT_REGION);
        accessKeyId = trimToNull(accessKeyId);
        accessKeySecret = trimToNull(accessKeySecret);
        securityToken = trimToNull(securityToken);
        signName = trimToNull(signName);
        templateCode = trimToNull(templateCode);
        templateParamName = defaultIfBlank(templateParamName, DEFAULT_TEMPLATE_PARAM);
        connectTimeoutMillis = normalizeTimeout(connectTimeoutMillis, DEFAULT_CONNECT_TIMEOUT_MILLIS);
        readTimeoutMillis = normalizeTimeout(readTimeoutMillis, DEFAULT_READ_TIMEOUT_MILLIS);
    }

    /** 缺失的必填键（仅键名；顺序稳定）。空列表表示配置完整。 */
    public List<String> missingRequiredKeys() {        List<String> missing = new ArrayList<>();
        if (accessKeyId == null) {
            missing.add("app.sms.aliyun.access-key-id");
        }
        if (accessKeySecret == null) {
            missing.add("app.sms.aliyun.access-key-secret");
        }
        if (signName == null) {
            missing.add("app.sms.aliyun.sign-name");
        }
        if (templateCode == null) {
            missing.add("app.sms.aliyun.template-code");
        }
        return missing;
    }

    /** 覆盖 record 自动 toString：绝不泄露凭据值（AccessKey/Secret/STS）。 */
    @Override
    public String toString() {
        return "AliyunSmsProperties[endpoint=" + endpoint + ", regionId=" + regionId
                + ", accessKeyId=" + redacted(accessKeyId)
                + ", accessKeySecret=" + redacted(accessKeySecret)
                + ", securityToken=" + redacted(securityToken)
                + ", signName=" + signName + ", templateCode=" + templateCode
                + ", templateParamName=" + templateParamName
                + ", connectTimeoutMillis=" + connectTimeoutMillis
                + ", readTimeoutMillis=" + readTimeoutMillis + "]";
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

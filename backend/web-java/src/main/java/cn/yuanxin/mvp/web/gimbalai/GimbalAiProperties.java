package cn.yuanxin.mvp.web.gimbalai;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.ArrayList;
import java.util.List;

/**
 * 云台 AI 文本透传配置（{@code app.gimbal-ai.*}）。<b>默认值写在代码里</b>。
 *
 * <p><b>安全</b>：本类只读环境/config；仓库内只允许安全占位（默认空 = 未配置），
 * 绝不硬编码真实服务 IP 或密钥。缺失校验只输出<b>键名</b>；{@link #toString()}
 * 对 api-key 脱敏。</p>
 *
 * <p>超时默认 connect 3s / read 10s（下游为同步问答，读取上限应在部署时按需调整）。</p>
 */
@ConfigurationProperties(prefix = "app.gimbal-ai")
public record GimbalAiProperties(
        String baseUrl,
        String apiKey,
        Integer connectTimeoutMillis,
        Integer readTimeoutMillis) {

    public static final int DEFAULT_CONNECT_TIMEOUT_MILLIS = 3000;
    public static final int DEFAULT_READ_TIMEOUT_MILLIS = 10000;
    public static final int MIN_TIMEOUT_MILLIS = 1000;

    public GimbalAiProperties {
        baseUrl = trimToNull(baseUrl);
        apiKey = trimToNull(apiKey);
        connectTimeoutMillis = normalizeTimeout(connectTimeoutMillis, DEFAULT_CONNECT_TIMEOUT_MILLIS);
        readTimeoutMillis = normalizeTimeout(readTimeoutMillis, DEFAULT_READ_TIMEOUT_MILLIS);
    }

    /** 缺失的必填键（仅键名，绝不回显值）。 */
    public List<String> missingRequiredKeys() {
        List<String> missing = new ArrayList<>();
        if (baseUrl == null) {
            missing.add("app.gimbal-ai.base-url");
        }
        if (apiKey == null) {
            missing.add("app.gimbal-ai.api-key");
        }
        return missing;
    }

    /** base-url 去掉结尾斜杠，避免与下游路径拼接出双斜杠。 */
    public String normalizedBaseUrl() {
        if (baseUrl == null) {
            return null;
        }
        return baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
    }

    @Override
    public String toString() {
        return "GimbalAiProperties[baseUrl=" + baseUrl
                + ", apiKey=" + (apiKey == null ? "<absent>" : "<redacted>")
                + ", connectTimeoutMillis=" + connectTimeoutMillis
                + ", readTimeoutMillis=" + readTimeoutMillis + "]";
    }

    private static Integer normalizeTimeout(Integer value, int fallback) {
        int normalized = value == null || value <= 0 ? fallback : value;
        return Math.max(MIN_TIMEOUT_MILLIS, normalized);
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}

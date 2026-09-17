package cn.yuanxin.mvp.web.assessments.narration;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.ArrayList;
import java.util.List;

/**
 * 报告播报下游配置（{@code app.report-narration.*}）。<b>默认值写在代码里</b>。
 *
 * <p><b>安全</b>：本类只读环境/config；仓库内只允许安全占位（默认空 = 未配置），
 * 绝不硬编码真实服务地址或密钥。缺失校验只输出<b>键名</b>；{@link #toString()}
 * 对 api-key 脱敏。base-url 被允许原样输出（它不是凭据），但仓库内默认必须为空。</p>
 *
 * <p><b>read-timeout 默认 30000ms 的理由</b>：它是 {@code TimeoutLineSource} 的
 * <b>每行/每次 poll</b> 超时（不是整段播报的总时长）。报告播报是长文本生成，逐段下发之间
 * 可能有较长停顿；{@code gimbalai} 的 10s 对其偏短。D 对同一 AI 服务的非流式 assess
 * 默认 30s（{@code dconfig.py:99}），取同一量级更稳妥。部署时可按需调整。</p>
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiProperties} 同源范式、刻意不共享
 * （抽共享包必须改动已交付并经审的 {@code web/gimbalai/**}）。</p>
 */
@ConfigurationProperties(prefix = "app.report-narration")
public record ReportNarrationProperties(
        String baseUrl,
        String apiKey,
        Integer connectTimeoutMillis,
        Integer readTimeoutMillis) {

    public static final int DEFAULT_CONNECT_TIMEOUT_MILLIS = 3000;
    public static final int DEFAULT_READ_TIMEOUT_MILLIS = 30000;
    public static final int MIN_TIMEOUT_MILLIS = 1000;

    public ReportNarrationProperties {
        baseUrl = trimToNull(baseUrl);
        apiKey = trimToNull(apiKey);
        connectTimeoutMillis = normalizeTimeout(connectTimeoutMillis, DEFAULT_CONNECT_TIMEOUT_MILLIS);
        readTimeoutMillis = normalizeTimeout(readTimeoutMillis, DEFAULT_READ_TIMEOUT_MILLIS);
    }

    /** 缺失的必填键（仅键名，绝不回显值）。 */
    public List<String> missingRequiredKeys() {
        List<String> missing = new ArrayList<>();
        if (baseUrl == null) {
            missing.add("app.report-narration.base-url");
        }
        if (apiKey == null) {
            missing.add("app.report-narration.api-key");
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
        return "ReportNarrationProperties[baseUrl=" + baseUrl
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

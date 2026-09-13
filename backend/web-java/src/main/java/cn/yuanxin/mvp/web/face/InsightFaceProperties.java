package cn.yuanxin.mvp.web.face;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * InsightFace 人脸服务配置（{@code app.face.insightface.*}）。<b>默认值写在代码里</b>。
 *
 * <p>示例 base-url（内网，仅文档示例、非默认值）：{@code http://10.3.6.163:8010}。</p>
 *
 * <p><b>安全：</b>缺失校验只输出<b>键名</b>；{@link #toString()} 与异常消息绝不回显 token。
 * token 推荐用 {@code internal-token-file}（根在部署机放置，仅进程可读）。</p>
 *
 * <p>read 超时默认 30s：远端模型首次加载/CPU 推理较慢，超时过短会误判依赖失败。</p>
 */
@ConfigurationProperties(prefix = "app.face.insightface")
public record InsightFaceProperties(
        String baseUrl,
        String namespace,
        String internalToken,
        String internalTokenFile,
        Integer connectTimeoutMillis,
        Integer readTimeoutMillis,
        Double verifyThreshold) {

    public static final int DEFAULT_CONNECT_TIMEOUT_MILLIS = 3000;
    public static final int DEFAULT_READ_TIMEOUT_MILLIS = 30000;
    public static final int MIN_TIMEOUT_MILLIS = 1000;

    public InsightFaceProperties {
        baseUrl = trimToNull(baseUrl);
        namespace = trimToNull(namespace);
        internalToken = trimToNull(internalToken);
        internalTokenFile = trimToNull(internalTokenFile);
        connectTimeoutMillis = normalizeTimeout(connectTimeoutMillis, DEFAULT_CONNECT_TIMEOUT_MILLIS);
        readTimeoutMillis = normalizeTimeout(readTimeoutMillis, DEFAULT_READ_TIMEOUT_MILLIS);
    }

    /** 缺失的必填键（仅键名）。token 二选一：两者皆无时列为缺失。 */
    public List<String> missingRequiredKeys() {
        List<String> missing = new ArrayList<>();
        if (baseUrl == null) {
            missing.add("app.face.insightface.base-url");
        }
        if (namespace == null) {
            missing.add("app.face.insightface.namespace");
        }
        if (internalToken == null && internalTokenFile == null) {
            missing.add("app.face.insightface.internal-token or app.face.insightface.internal-token-file");
        }
        return missing;
    }

    /** 两种 token 来源同时配置 → 拒绝启动（配置歧义）。 */
    public boolean tokenSourcesConflict() {
        return internalToken != null && internalTokenFile != null;
    }

    /** 解析 token（内联优先；否则读文件）。绝不把值写入日志/消息。 */
    public String resolvedToken() {
        if (internalToken != null) {
            return internalToken;
        }
        if (internalTokenFile == null) {
            return null;
        }
        try {
            String value = Files.readString(Path.of(internalTokenFile), StandardCharsets.UTF_8).trim();
            if (value.isEmpty()) {
                throw new IllegalStateException(
                        "app.face.insightface.internal-token-file is empty; provide a token (value not logged)");
            }
            return value;
        } catch (IOException unreadable) {
            throw new IllegalStateException("app.face.insightface.internal-token-file could not be read"
                    + " (path not logged); provide a readable token file");
        }
    }

    @Override
    public String toString() {
        return "InsightFaceProperties[baseUrl=" + baseUrl + ", namespace=" + namespace
                + ", internalToken=" + (internalToken == null ? "<absent>" : "<redacted>")
                + ", internalTokenFile=" + (internalTokenFile == null ? "<absent>" : "<set>")
                + ", connectTimeoutMillis=" + connectTimeoutMillis
                + ", readTimeoutMillis=" + readTimeoutMillis
                + ", verifyThreshold=" + verifyThreshold + "]";
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

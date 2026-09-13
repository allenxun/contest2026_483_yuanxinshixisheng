package cn.yuanxin.mvp.web.sms;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 真实短信风控参数（{@code app.sms.risk.*}；默认值写在代码里）。仅 {@code aliyun}
 * 提供方使用；{@code doubles} 替身行为完全不变。
 *
 * <p>默认对齐官方验证码频控（同一签名 + 同一手机号）：<b>1 分钟 1 条、1 小时 5 条、
 * 1 天 10 条</b>。窗口按 <b>UTC+8 自然分钟/小时/日</b> 计算（非滚动窗口）。</p>
 *
 * <p><b>这是本地预检</b>：用于在调用计费接口前尽早拒绝；平台仍可能返回
 * {@code isv.BUSINESS_LIMIT_CONTROL} 等平台流控，此时适配器按 {@link FailureKind#THROTTLED}
 * 映射为 429，本层不因此放宽。</p>
 */
@ConfigurationProperties(prefix = "app.sms.risk")
public record SmsRiskProperties(
        Integer challengeTtlSeconds,
        Integer maxVerifyAttempts,
        Integer maxPerMinute,
        Integer maxPerHour,
        Integer maxPerDay,
        Integer retryAfterSeconds) {

    public static final int DEFAULT_CHALLENGE_TTL_SECONDS = 300;
    public static final int DEFAULT_MAX_VERIFY_ATTEMPTS = 5;
    public static final int DEFAULT_MAX_PER_MINUTE = 1;
    public static final int DEFAULT_MAX_PER_HOUR = 5;
    public static final int DEFAULT_MAX_PER_DAY = 10;
    public static final int DEFAULT_RETRY_AFTER_SECONDS = 60;

    public SmsRiskProperties {
        challengeTtlSeconds = positive(challengeTtlSeconds, DEFAULT_CHALLENGE_TTL_SECONDS);
        maxVerifyAttempts = positive(maxVerifyAttempts, DEFAULT_MAX_VERIFY_ATTEMPTS);
        maxPerMinute = nonNegative(maxPerMinute, DEFAULT_MAX_PER_MINUTE);
        maxPerHour = nonNegative(maxPerHour, DEFAULT_MAX_PER_HOUR);
        maxPerDay = nonNegative(maxPerDay, DEFAULT_MAX_PER_DAY);
        retryAfterSeconds = positive(retryAfterSeconds, DEFAULT_RETRY_AFTER_SECONDS);
    }

    private static int positive(Integer value, int fallback) {
        return value == null || value <= 0 ? fallback : value;
    }

    private static int nonNegative(Integer value, int fallback) {
        return value == null || value < 0 ? fallback : value;
    }
}

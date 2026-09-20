package cn.yuanxin.mvp.web.sms;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

/**
 * 短信节流窗口的 UTC+8 自然边界归一（分钟 / 小时 / 日）。
 *
 * <p>两个后端共用本类，保证"内存实现"与"Redis 实现"对窗口边界、桶名与剩余时间的理解
 * <b>逐字一致</b>；若不共用，跨实例窗口错位与内存/Redis 行为漂移都会难以察觉。</p>
 *
 * <p>内存实现仍按 {@code sameMinute/sameHour/sameDay} 对历史时间戳过滤（逐字保留旧语义）；
 * Redis 实现用本类给出的桶名（如 {@code 202609141230}）构造计数键。两者对固定自然窗口等价。</p>
 */
final class SmsThrottleWindows {

    /** 官方短信验证码频控窗口按 UTC+8 自然分钟/小时/日。 */
    static final ZoneOffset CN_OFFSET = ZoneOffset.ofHours(8);

    /**
     * 计数键 TTL 相对窗口边界的余量（秒）：容忍多实例之间的轻微时钟偏移。
     * 桶名按各自时钟归一，键多活几秒不会造成跨桶串读。
     */
    static final long TTL_MARGIN_SECONDS = 5L;

    private static final DateTimeFormatter MINUTE_BUCKET = DateTimeFormatter.ofPattern("yyyyMMddHHmm");
    private static final DateTimeFormatter HOUR_BUCKET = DateTimeFormatter.ofPattern("yyyyMMddHH");
    private static final DateTimeFormatter DAY_BUCKET = DateTimeFormatter.ofPattern("yyyyMMdd");

    private SmsThrottleWindows() {
    }

    /** 三个窗口的桶名、键 TTL 与耗尽时的 retry-after（全部按 UTC+8 自然边界）。 */
    record Snapshot(String minuteBucket, String hourBucket, String dayBucket,
                    long minuteTtlSeconds, long hourTtlSeconds, long dayTtlSeconds,
                    long minuteRetryAfterSeconds, long hourRetryAfterSeconds, long dayRetryAfterSeconds) {
    }

    static Snapshot compute(Instant now) {
        ZonedDateTime nowCn = now.atZone(CN_OFFSET);
        long retryMinute = secondsToNextMinute(nowCn);
        long retryHour = secondsToNextHour(nowCn);
        long retryDay = secondsToNextDay(nowCn);
        return new Snapshot(
                nowCn.format(MINUTE_BUCKET), nowCn.format(HOUR_BUCKET), nowCn.format(DAY_BUCKET),
                retryMinute + TTL_MARGIN_SECONDS, retryHour + TTL_MARGIN_SECONDS,
                retryDay + TTL_MARGIN_SECONDS,
                retryMinute, retryHour, retryDay);
    }

    static boolean sameMinute(Instant instant, ZonedDateTime nowCn) {
        return instant.atZone(CN_OFFSET).truncatedTo(ChronoUnit.MINUTES)
                .equals(nowCn.truncatedTo(ChronoUnit.MINUTES));
    }

    static boolean sameHour(Instant instant, ZonedDateTime nowCn) {
        return instant.atZone(CN_OFFSET).truncatedTo(ChronoUnit.HOURS)
                .equals(nowCn.truncatedTo(ChronoUnit.HOURS));
    }

    static boolean sameDay(Instant instant, ZonedDateTime nowCn) {
        return instant.atZone(CN_OFFSET).toLocalDate().equals(nowCn.toLocalDate());
    }

    static long secondsToNextMinute(ZonedDateTime nowCn) {
        return Math.max(1, 60L - nowCn.getSecond());
    }

    static long secondsToNextHour(ZonedDateTime nowCn) {
        long elapsed = nowCn.getMinute() * 60L + nowCn.getSecond();
        return Math.max(1, 3600L - elapsed);
    }

    static long secondsToNextDay(ZonedDateTime nowCn) {
        ZonedDateTime nextDay = nowCn.toLocalDate().plusDays(1).atStartOfDay(CN_OFFSET);
        return Math.max(1, Duration.between(nowCn, nextDay).getSeconds());
    }
}

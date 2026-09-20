package cn.yuanxin.mvp.web.sms;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;

/** 测试用可推进时钟（避免 sleep）。 */
final class MutableClock extends Clock {

    private volatile Instant instant;
    private final ZoneId zone;

    MutableClock(Instant start, ZoneId zone) {
        this.instant = start;
        this.zone = zone;
    }

    void advance(Duration duration) {
        this.instant = this.instant.plus(duration);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableClock(instant, newZone);
    }

    @Override
    public Instant instant() {
        return instant;
    }
}

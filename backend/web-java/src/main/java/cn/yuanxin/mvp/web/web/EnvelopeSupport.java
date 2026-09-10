package cn.yuanxin.mvp.web.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

/**
 * 信封构造辅助：requestId 取自 RequestIdFilter 属性；replayed 取自 T13
 * 重放标记（请求属性）；serverTime 为 RFC3339 UTC（秒精度）。
 */
@Component
public class EnvelopeSupport {

    /** T13 succeeded 重放时由控制器置 true，信封 meta.replayed 读取。 */
    public static final String ATTR_REPLAYED = "mvp.replayed";

    public static String requestId(HttpServletRequest request) {
        Object v = request.getAttribute(RequestIdFilter.ATTR_REQUEST_ID);
        return v == null ? "" : v.toString();
    }

    public static String rfc3339(Instant instant) {
        return instant.truncatedTo(ChronoUnit.SECONDS).toString();
    }

    public SuccessEnvelope ok(HttpServletRequest request, Object data) {
        boolean replayed = Boolean.TRUE.equals(request.getAttribute(ATTR_REPLAYED));
        return SuccessEnvelope.of(requestId(request), data, replayed, rfc3339(Instant.now()));
    }

    public SuccessEnvelope ok(HttpServletRequest request, Object data, boolean explicitReplayed) {
        return SuccessEnvelope.of(requestId(request), data, explicitReplayed, rfc3339(Instant.now()));
    }

    public ErrorEnvelope error(HttpServletRequest request, ErrorEnvelope.ErrorBody body) {
        return new ErrorEnvelope(requestId(request), body);
    }
}

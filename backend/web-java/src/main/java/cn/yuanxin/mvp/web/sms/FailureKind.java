package cn.yuanxin.mvp.web.sms;

import java.util.Set;

/**
 * 阿里云短信失败分类（用于把平台业务 Code / 异常映射为 HTTP 语义）。
 *
 * <p>分类仅依据官方短信错误码前缀（见 {@code B-sms-aliyun.md}）：</p>
 * <ul>
 *   <li>{@link #THROTTLED}：平台流控/频控（本地节流之外的二次防线）→ 429 RATE_LIMITED；</li>
 *   <li>{@link #CONFIGURATION}：签名/模板/参数/权限/凭据类错误，重试无意义 → 503（不承诺可重试）；</li>
 *   <li>{@link #DEPENDENCY}：余额/服务/系统/网络超时等依赖类 → 503（可退避重试，但短信非幂等）。</li>
 * </ul>
 */
public enum FailureKind {

    THROTTLED,
    CONFIGURATION,
    DEPENDENCY;

    private static final Set<String> THROTTLED_CODES = Set.of(
            "isv.BUSINESS_LIMIT_CONTROL",
            "isv.MOBILE_COUNT_OVER_LIMIT",
            "isv.DAY_LIMIT_CONTROL",
            "isv.MONTH_LIMIT_CONTROL");

    private static final Set<String> CONFIGURATION_CODES = Set.of(
            "isv.SMS_SIGNATURE_ILLEGAL",
            "isv.SMS_TEMPLATE_ILLEGAL",
            "isv.INVALID_JSON_PARAM",
            "isv.TEMPLATE_MISSING_PARAMETERS",
            "isv.MOBILE_NUMBER_ILLEGAL",
            "isp.RAM_PERMISSION_DENY",
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
            "Forbidden",
            "Unauthorized");

    private static final Set<String> DEPENDENCY_CODES = Set.of(
            "isv.AMOUNT_NOT_ENOUGH",
            "isv.OUT_OF_SERVICE",
            "isp.SYSTEM_ERROR");

    /** 未知/空 Code 保守归为依赖类（503，可观察后重试），绝不视为成功。 */
    public static FailureKind classify(String code) {
        if (code == null || code.isBlank()) {
            return DEPENDENCY;
        }
        String normalized = code.trim();
        if (THROTTLED_CODES.contains(normalized)) {
            return THROTTLED;
        }
        if (CONFIGURATION_CODES.contains(normalized)) {
            return CONFIGURATION;
        }
        if (DEPENDENCY_CODES.contains(normalized)) {
            return DEPENDENCY;
        }
        return DEPENDENCY;
    }
}

package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;

import java.util.regex.Pattern;

/**
 * bigint 十进制字符串的契约化解析/输出（DD 3.1；contracts BigintString）。
 *
 * <p>契约 pattern {@code ^(0|[1-9][0-9]*)$}：只接受无符号十进制、无前导零
 * （"0" 合法）；非法/前导零/超 long 一律 400 INVALID_INPUT。</p>
 */
public final class CareBigints {

    private static final Pattern DECIMAL = Pattern.compile("^(0|[1-9][0-9]*)$");

    private CareBigints() {
    }

    /** 解析必填 bigint 字符串；非法/溢出 → 400 INVALID_INPUT。 */
    public static long parse(String raw, String field) {
        if (raw == null || !DECIMAL.matcher(raw).matches()) {
            throw invalid(field);
        }
        try {
            return Long.parseLong(raw);
        } catch (NumberFormatException overflow) {
            throw invalid(field);
        }
    }

    /** 解析可空 bigint 字符串；null → null，非法/溢出 → 400 INVALID_INPUT。 */
    public static Long parseNullable(String raw, String field) {
        return raw == null ? null : parse(raw, field);
    }

    /** 输出 bigint（必填）。 */
    public static String out(long value) {
        return Long.toString(value);
    }

    /** 输出 bigint（可空）。 */
    public static String out(Long value) {
        return value == null ? null : Long.toString(value);
    }

    private static ApiException invalid(String field) {
        return new ApiException(ErrorCode.INVALID_INPUT,
                field + " must be an unsigned decimal bigint string", java.util.Map.of("field", field));
    }
}

package cn.yuanxin.mvp.web.sms;

/**
 * 日志脱敏工具：手机号<b>绝不</b>完整落日志。验证码由调用方保证不记录。
 */
final class SmsMasking {

    private SmsMasking() {
    }

    /** 例：{@code +8610000000000} → {@code +861****0000}；异常短输入 → {@code ***}。 */
    static String maskPhone(String phone) {
        if (phone == null || phone.isBlank()) {
            return "<none>";
        }
        String value = phone.trim();
        if (value.length() <= 7) {
            return "***";
        }
        return value.substring(0, 4) + "****" + value.substring(value.length() - 4);
    }
}

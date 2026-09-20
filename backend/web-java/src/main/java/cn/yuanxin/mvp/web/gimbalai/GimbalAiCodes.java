package cn.yuanxin.mvp.web.gimbalai;

import java.util.regex.Pattern;

/**
 * 下游诊断码的安全归一：只允许 {@code ^[A-Z0-9_]{1,64}$}。
 *
 * <p>任何来自下游的不受信字符串（problem+json {@code code}、{@code response.failed.code}）
 * 都必须先经此过滤，才可能进入日志/异常携带字段；不匹配（超长、含控制字符/空格/用户文本、
 * 小写或任意标点）一律归一为 {@code null}，由调用方记为 {@code <none>}。这堵住
 * "下游畸形码把任意载荷反射进日志" 的通道。</p>
 */
final class GimbalAiCodes {

    private static final Pattern SAFE_CODE = Pattern.compile("^[A-Z0-9_]{1,64}$");

    private GimbalAiCodes() {
    }

    /** @return 归一化后的安全码；不匹配返回 {@code null} */
    static String sanitize(String raw) {
        if (raw == null) {
            return null;
        }
        String trimmed = raw.trim();
        return SAFE_CODE.matcher(trimmed).matches() ? trimmed : null;
    }
}

package cn.yuanxin.mvp.web.state;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/**
 * 状态后端的<b>键模型</b>（唯一权威）。所有 Redis 键都必须经本类构造，禁止在业务代码里手拼字符串，
 * 以免键形状漂移导致"旧键读不到"或"清理漏删"。
 *
 * <p><b>键通则</b>：</p>
 * <ol>
 *   <li>形状 = {@code <prefix><域>:<用途>:<标识>}；</li>
 *   <li><b>凭据与 PII 一律以 sha256 十六进制摘要入键</b>（access/refresh token、手机号）。
 *       原因：键会出现在 {@code SCAN}、慢日志、监控与运维排障输出里，原文 token 一旦入键
 *       就等于把持有者凭据散布到可观测面；</li>
 *   <li><b>每个键只用一种 Redis 类型</b>。实测：对 list 做 {@code GET} → {@code WRONGTYPE}；
 *       对非整数字符串做 {@code INCR} → {@code ERR value is not an integer or out of range}。
 *       因此键名带明确用途段，绝不复用同名键承载不同类型；</li>
 *   <li>{@code sessionId} <b>不</b>做摘要：它是服务端生成的随机 UUID、不含用户身份，
 *       且要作为 T09 {@code notification_destinations.session_ref} 与 T13
 *       {@code principal_id} 的一部分被业务使用，必须保持原值可返回。</li>
 * </ol>
 *
 * <p><b>验证码摘要</b>：{@link #codeDigest(String, String)} 以 {@code challengeId} 为盐，
 * 因此<b>明文验证码绝不落入 Redis</b>（比现状的内存明文更严格）：即使 Redis 被导出也拿不到
 * 可用验证码，且相同验证码在不同 challenge 下摘要不同，无法建立全局对照表。</p>
 *
 * <p><b>关于常量时间比较</b>：验证码比较发生在 Lua 内、对<b>定长 sha256 摘要</b>做等值判断。
 * 这里不再使用 {@code MessageDigest.isEqual} 是<b>有意且安全</b>的：被比较的值是 256 位摘要而非
 * 6 位明文码，攻击者无法从摘要等值判断的时序反推验证码（需先找到 sha256 原像）；定长摘要也消除了
 * 长度泄漏。把比较移出 Java 是原子性的<b>必要代价</b>——否则"比较"与"核销/计数"会退化成两步，
 * 重新打开并发核销的竞态窗口。</p>
 */
public final class StateKeys {

    /** 默认命名空间前缀（{@code app.state.redis.key-prefix} 未配置时使用）。 */
    public static final String DEFAULT_PREFIX = "mvp:b:";

    /** 前缀长度上限：过长的前缀会无谓放大每个键的内存占用。 */
    public static final int MAX_PREFIX_LENGTH = 64;

    private static final String SESSION_ACCESS = "sess:at:";
    private static final String SESSION_REFRESH = "sess:rt:";
    private static final String SESSION_BY_ID = "sess:sid:";
    private static final String SMS_CHALLENGE = "sms:ch:";
    private static final String SMS_RATE_LIMIT = "sms:rl:";

    private final String prefix;

    public StateKeys(String prefix) {
        this.prefix = normalizePrefix(prefix);
    }

    /** 归一化后的命名空间前缀（保证非空且以 {@code :} 结尾）。 */
    public String prefix() {
        return prefix;
    }

    /**
     * 归一化并校验前缀：null/空白 → {@link #DEFAULT_PREFIX}；trim 后若不以 {@code :} 结尾则补上；
     * 拒绝含空白或 glob 元字符（{@code * ? [ ]}）的前缀——否则会污染 {@link #pattern(String)}
     * 的 {@code SCAN} 匹配语义，导致测试清理误删他人键。
     */
    public static String normalizePrefix(String raw) {
        if (raw == null || raw.isBlank()) {
            return DEFAULT_PREFIX;
        }
        String value = raw.trim();
        if (value.length() > MAX_PREFIX_LENGTH) {
            throw new IllegalArgumentException("invalid " + AppStateProperties.KEY_PREFIX_KEY
                    + ": length must be <= " + MAX_PREFIX_LENGTH + " characters");
        }
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (Character.isWhitespace(c) || c == '*' || c == '?' || c == '[' || c == ']') {
                throw new IllegalArgumentException("invalid " + AppStateProperties.KEY_PREFIX_KEY
                        + ": must not contain whitespace or glob metacharacters (* ? [ ])");
            }
        }
        return value.endsWith(":") ? value : value + ":";
    }

    /**
     * 校验并拼接一个<b>服务端自己生成</b>的标识段（sessionId、challengeId）。
     * 拒绝空白与 glob 元字符，理由同 {@link #normalizePrefix(String)}。
     */
    private static String safeIdentifier(String value, String what) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(what + " must not be blank");
        }
        String trimmed = value.trim();
        for (int i = 0; i < trimmed.length(); i++) {
            char c = trimmed.charAt(i);
            if (Character.isWhitespace(c) || c == '*' || c == '?' || c == '[' || c == ']') {
                throw new IllegalArgumentException(what + " must not contain whitespace"
                        + " or glob metacharacters (* ? [ ])");
            }
        }
        return trimmed;
    }

    /** sha256 十六进制摘要（小写）。用于 token 与手机号入键，绝不使用原文。 */
    public static String sha256Hex(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value to digest must not be null");
        }
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            // SHA-256 是 JVM 规范强制要求的算法；到这里说明运行环境异常，不静默降级。
            throw new IllegalStateException("SHA-256 is unavailable in this JVM", e);
        }
    }

    /**
     * 验证码的存储/比较摘要：{@code sha256(code + "|" + challengeId)}。
     * 以 challengeId 为盐 ⇒ 明文码不落 Redis，且相同码在不同 challenge 下摘要不同。
     */
    public static String codeDigest(String code, String challengeId) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code must not be blank");
        }
        return sha256Hex(code + "|" + safeIdentifier(challengeId, "challengeId"));
    }

    /** access token → 会话记录键（hash）。{@code authenticate} 的唯一查询路径。 */
    public String sessionByAccessToken(String accessToken) {
        return prefix + SESSION_ACCESS + sha256Hex(requireToken(accessToken, "accessToken"));
    }

    /** refresh token → sessionId 键（string）。一次性轮换的 CAS 目标。 */
    public String sessionByRefreshToken(String refreshToken) {
        return prefix + SESSION_REFRESH + sha256Hex(requireToken(refreshToken, "refreshToken"));
    }

    /** sessionId → access token 摘要键（string）。轮换/撤销时定位旧 access token。 */
    public String sessionById(String sessionId) {
        return prefix + SESSION_BY_ID + safeIdentifier(sessionId, "sessionId");
    }

    /** challengeId → 验证码挑战键（hash：摘要、手机号、过期时刻、尝试次数）。 */
    public String smsChallenge(String challengeId) {
        return prefix + SMS_CHALLENGE + safeIdentifier(challengeId, "challengeId");
    }

    /**
     * 手机号 + 窗口 + 自然窗口桶 → 限流计数键（string 整数）。
     *
     * @param window 窗口标识（如 {@code m}/{@code h}/{@code d}）
     * @param bucket 按 UTC+8 自然边界格式化的桶名（如 {@code 202609141230}）
     */
    public String smsRateLimit(String phone, String window, String bucket) {
        return prefix + SMS_RATE_LIMIT + sha256Hex(requireToken(phone, "phone"))
                + ":" + safeIdentifier(window, "window") + ":" + safeIdentifier(bucket, "bucket");
    }

    /**
     * 供<b>测试清理</b>使用的 {@code SCAN} 匹配模式：{@code <prefix><domainGlob>}。
     * 只应传入本实例自己的前缀派生模式；<b>绝不</b>用 {@code FLUSHDB}/{@code FLUSHALL}。
     */
    public String pattern(String domainGlob) {
        return prefix + (domainGlob == null ? "*" : domainGlob);
    }

    private static String requireToken(String value, String what) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(what + " must not be blank");
        }
        return value;
    }

    @Override
    public String toString() {
        // 前缀是命名空间而非秘密，但仍不回显完整键（键含摘要，回显无诊断价值）。
        return "StateKeys[prefix=" + prefix + "]";
    }
}

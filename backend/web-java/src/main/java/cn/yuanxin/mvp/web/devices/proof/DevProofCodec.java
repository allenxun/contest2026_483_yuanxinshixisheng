package cn.yuanxin.mvp.web.devices.proof;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * B 自有 skeleton 证明编解码器（<b>仅供 dev/test 替身与测试构造证明</b>）。
 *
 * <p>真实设备配对/连接协议（签名算法、密钥预置/轮换、nonce 存储）尚未冻结。
 * 本类定义一个明确命名的开发格式，使替身能产生六种可区分输入：</p>
 *
 * <pre>
 * proof = "&lt;version&gt;.&lt;base64url(payloadJson)&gt;.&lt;base64url(hmacSha256(key, payloadB64))&gt;"
 * version = "d1"（其余 dN → UNSUPPORTED_VERSION）
 * payload = {purpose, gimbalId, accountId, installationId, microcrystalSerial,
 *            observerType, observerRef, exp(epochSeconds), nonce}
 * </pre>
 *
 * <p>签名与格式校验失败可区分（BAD_SIGNATURE vs MALFORMED）；本类绝不
 * 用于生产（生产由 fail-closed 校验要求真实实现）。测试可用
 * {@link #DEV_TEST_KEY} 与 {@link #encode(String, Map, String)} 构造输入。</p>
 */
public final class DevProofCodec {

    /** dev/test 固定对称密钥（仅 skeleton；生产严禁使用）。 */
    public static final String DEV_TEST_KEY = "mvp-b-dev-test-proof-key-v1";

    public static final String VERSION = "d1";

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final TypeReference<Map<String, Object>> MAP_TYPE =
            new TypeReference<Map<String, Object>>() {
            };
    private static final Pattern VERSION_PATTERN = Pattern.compile("^d[0-9]+$");

    private DevProofCodec() {
    }

    /** 解析结果：版本、payload、签名是否匹配（结构可解析但签名错也返回本记录）。 */
    public record Decoded(String version, Map<String, Object> payload, boolean signatureValid) {
    }

    public static String encode(Map<String, Object> payload, String key) {
        return encode(VERSION, payload, key);
    }

    public static String encode(String version, Map<String, Object> payload, String key) {
        try {
            String payloadB64 = Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(MAPPER.writeValueAsBytes(payload));
            String signature = sign(payloadB64, key);
            return version + "." + payloadB64 + "." + signature;
        } catch (Exception e) {
            throw new IllegalStateException("dev proof encoding failed", e);
        }
    }

    /** 结构非法（非三段/版本 token 非法/非法 base64/非法 JSON）→ null。 */
    public static Decoded decode(String proof) {
        if (proof == null || proof.isBlank()) {
            return null;
        }
        String[] parts = proof.split("\\.", -1);
        if (parts.length != 3 || !VERSION_PATTERN.matcher(parts[0]).matches()) {
            return null;
        }
        try {
            byte[] payloadBytes = Base64.getUrlDecoder().decode(parts[1]);
            Map<String, Object> payload = MAPPER.readValue(payloadBytes, MAP_TYPE);
            if (payload == null) {
                return null;
            }
            String expected = sign(parts[1], DEV_TEST_KEY);
            return new Decoded(parts[0], payload, MessageDigest.isEqual(
                    expected.getBytes(StandardCharsets.UTF_8),
                    parts[2].getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            return null;
        }
    }

    private static String sign(String payloadB64, String key) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal(payloadB64.getBytes(StandardCharsets.UTF_8)));
    }
}

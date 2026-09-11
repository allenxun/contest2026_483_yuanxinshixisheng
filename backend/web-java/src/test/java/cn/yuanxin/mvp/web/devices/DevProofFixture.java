package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.devices.proof.DevProofCodec;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * 测试侧证明构造器：用 B 自有 skeleton 格式生成六种可区分输入
 * （valid / bad signature / expired / bound to another gimbal /
 * bound to another account-installation / nonce replay）+ malformed /
 * unsupported-version / wrong-microcrystal 细分。
 *
 * <p>仅供测试；生产协议冻结后由设备团队提供真实签名器替换。</p>
 */
final class DevProofFixture {

    private DevProofFixture() {
    }

    private static Map<String, Object> base(String purpose, long exp) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("purpose", purpose);
        payload.put("gimbalId", null);
        payload.put("accountId", null);
        payload.put("installationId", null);
        payload.put("microcrystalSerial", null);
        payload.put("observerType", null);
        payload.put("observerRef", null);
        payload.put("exp", exp);
        payload.put("nonce", UUID.randomUUID().toString());
        return payload;
    }

    private static long future() {
        return Instant.now().getEpochSecond() + 300;
    }

    private static String encode(Map<String, Object> payload) {
        return DevProofCodec.encode(payload, DevProofCodec.DEV_TEST_KEY);
    }

    private static String tamperSignature(String proof) {
        char last = proof.charAt(proof.length() - 1);
        return proof.substring(0, proof.length() - 1) + (last == 'A' ? 'B' : 'A');
    }

    // ---------------- pairingProof ----------------

    static String pairingValid(UUID gimbal, UUID account, String installationId) {
        return encode(pairingPayload(gimbal, account, installationId));
    }

    private static Map<String, Object> pairingPayload(UUID gimbal, UUID account,
                                                       String installationId) {
        Map<String, Object> payload = base("pairing", future());
        payload.put("gimbalId", gimbal.toString());
        payload.put("accountId", account.toString());
        payload.put("installationId", installationId);
        return payload;
    }

    static String pairingBadSignature(UUID gimbal, UUID account, String installationId) {
        return tamperSignature(pairingValid(gimbal, account, installationId));
    }

    static String pairingExpired(UUID gimbal, UUID account, String installationId) {
        Map<String, Object> payload = base("pairing", Instant.now().getEpochSecond() - 60);
        payload.put("gimbalId", gimbal.toString());
        payload.put("accountId", account.toString());
        payload.put("installationId", installationId);
        return encode(payload);
    }

    static String pairingWrongGimbal(UUID account, String installationId) {
        return encode(pairingPayload(UUID.randomUUID(), account, installationId));
    }

    static String pairingWrongAccount(UUID gimbal, String installationId) {
        return encode(pairingPayload(gimbal, UUID.randomUUID(), installationId));
    }

    static String pairingUnsupportedVersion(UUID gimbal, UUID account, String installationId) {
        return DevProofCodec.encode("d2", pairingPayload(gimbal, account, installationId),
                DevProofCodec.DEV_TEST_KEY);
    }

    static String malformedProof() {
        return "not-a-valid-proof";
    }

    // ---------------- connectionProof ----------------

    static String connectionApp(UUID account, String installationId, String serial) {
        Map<String, Object> payload = base("connection", future());
        payload.put("observerType", "app_account");
        payload.put("observerRef", account + ":" + installationId);
        payload.put("accountId", account.toString());
        payload.put("installationId", installationId);
        payload.put("microcrystalSerial", serial);
        return encode(payload);
    }

    static String connectionGimbal(UUID gimbal, String serial) {
        Map<String, Object> payload = base("connection", future());
        payload.put("observerType", "gimbal");
        payload.put("observerRef", gimbal.toString());
        payload.put("gimbalId", gimbal.toString());
        payload.put("microcrystalSerial", serial);
        return encode(payload);
    }

    static String connectionBadSignature(UUID account, String installationId, String serial) {
        return tamperSignature(connectionApp(account, installationId, serial));
    }

    static String connectionExpired(UUID account, String installationId, String serial) {
        Map<String, Object> payload = base("connection", Instant.now().getEpochSecond() - 60);
        payload.put("observerType", "app_account");
        payload.put("observerRef", account + ":" + installationId);
        payload.put("accountId", account.toString());
        payload.put("installationId", installationId);
        payload.put("microcrystalSerial", serial);
        return encode(payload);
    }

    static String connectionWrongObserver(String serialNo) {
        Map<String, Object> payload = base("connection", future());
        payload.put("observerType", "app_account");
        payload.put("observerRef", UUID.randomUUID() + ":ghost-install");
        payload.put("accountId", UUID.randomUUID().toString());
        payload.put("installationId", "ghost-install");
        payload.put("microcrystalSerial", serialNo);
        return encode(payload);
    }

    static String connectionWrongGimbal(UUID serial, String serialNo) {
        Map<String, Object> payload = base("connection", future());
        payload.put("observerType", "gimbal");
        payload.put("observerRef", UUID.randomUUID().toString());
        payload.put("gimbalId", UUID.randomUUID().toString());
        payload.put("microcrystalSerial", serialNo);
        return encode(payload);
    }

    static String connectionWrongMicrocrystal(UUID account, String installationId, String serial) {
        Map<String, Object> payload = base("connection", future());
        payload.put("observerType", "app_account");
        payload.put("observerRef", account + ":" + installationId);
        payload.put("accountId", account.toString());
        payload.put("installationId", installationId);
        payload.put("microcrystalSerial", serial + "-other");
        return encode(payload);
    }

    static String connectionUnsupportedVersion(UUID account, String installationId, String serial) {
        Map<String, Object> payload = base("connection", future());
        payload.put("observerType", "app_account");
        payload.put("observerRef", account + ":" + installationId);
        payload.put("accountId", account.toString());
        payload.put("installationId", installationId);
        payload.put("microcrystalSerial", serial);
        return DevProofCodec.encode("d2", payload, DevProofCodec.DEV_TEST_KEY);
    }
}

package cn.yuanxin.mvp.web.devices.proof;

import cn.yuanxin.mvp.web.devices.DeviceJson;

import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 配对证明 dev/test 替身（仅 dev/test profile）。
 *
 * <p>校验 {@link DevProofCodec} 格式：版本、HMAC 签名、purpose=pairing、
 * 有效期、目标云台、账号/安装实例，并对 nonce 做"同 nonce 二次使用被拒"的
 * 内存重放检测（不新建表，符合写边界）。可产生：
 * valid / BAD_SIGNATURE / EXPIRED / WRONG_GIMBAL / WRONG_ACCOUNT / NONCE_REPLAY /
 * MALFORMED / UNSUPPORTED_VERSION 八种可区分输入。</p>
 */
public class DevTestDoublePairingProofVerifier implements PairingProofVerifier {

    private final Set<String> usedNonces = ConcurrentHashMap.newKeySet();

    @Override
    public Result verify(String proof, UUID expectedGimbalId, UUID accountId, String installationId) {
        if (proof == null || proof.isBlank()) {
            return Result.failed(ProofFailure.MISSING);
        }
        DevProofCodec.Decoded decoded = DevProofCodec.decode(proof);
        if (decoded == null) {
            return Result.failed(ProofFailure.MALFORMED);
        }
        if (!DevProofCodec.VERSION.equals(decoded.version())) {
            return Result.failed(ProofFailure.UNSUPPORTED_VERSION);
        }
        if (!decoded.signatureValid()) {
            return Result.failed(ProofFailure.BAD_SIGNATURE);
        }
        Map<String, Object> payload = decoded.payload();
        if (!"pairing".equals(DeviceJson.textAt(payload, "purpose"))) {
            return Result.failed(ProofFailure.MALFORMED);
        }
        Long exp = DeviceJson.longAt(payload, "exp");
        if (exp == null) {
            return Result.failed(ProofFailure.MALFORMED);
        }
        if (exp <= Instant.now().getEpochSecond()) {
            return Result.failed(ProofFailure.EXPIRED);
        }
        if (expectedGimbalId == null
                || !expectedGimbalId.toString().equals(DeviceJson.textAt(payload, "gimbalId"))) {
            return Result.failed(ProofFailure.WRONG_GIMBAL);
        }
        String payloadAccount = DeviceJson.textAt(payload, "accountId");
        String payloadInstallation = DeviceJson.textAt(payload, "installationId");
        if (accountId == null || !accountId.toString().equals(payloadAccount)
                || installationId == null || !installationId.equals(payloadInstallation)) {
            return Result.failed(ProofFailure.WRONG_ACCOUNT);
        }
        String nonce = DeviceJson.textAt(payload, "nonce");
        if (nonce == null || nonce.isBlank()) {
            return Result.failed(ProofFailure.MALFORMED);
        }
        if (!usedNonces.add(nonce)) {
            return Result.failed(ProofFailure.NONCE_REPLAY);
        }
        return Result.valid();
    }
}

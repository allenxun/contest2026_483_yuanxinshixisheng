package cn.yuanxin.mvp.web.devices.proof;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.devices.DeviceJson;

import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 连接证明 dev/test 替身（仅 dev/test profile）。
 *
 * <p>控制端期望值由 {@link PrincipalContext} 服务端派生（APP 用
 * {@code app_account + "<accountUuid>:<installationId>"}，云台用
 * {@code gimbal + "<gimbalUuid>"}）；请求体不参与。可产生 valid /
 * BAD_SIGNATURE / EXPIRED / WRONG_GIMBAL / WRONG_ACCOUNT / WRONG_MICROCRYSTAL /
 * NONCE_REPLAY / MALFORMED / UNSUPPORTED_VERSION 可区分输入，并对 nonce
 * 做内存重放检测。</p>
 */
public class DevTestDoubleConnectionProofVerifier implements ConnectionProofVerifier {

    private final Set<String> usedNonces = ConcurrentHashMap.newKeySet();

    @Override
    public Result verify(String proof, PrincipalContext principal, String microcrystalSerial) {
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
        if (!"connection".equals(DeviceJson.textAt(payload, "purpose"))) {
            return Result.failed(ProofFailure.MALFORMED);
        }
        Long exp = DeviceJson.longAt(payload, "exp");
        if (exp == null) {
            return Result.failed(ProofFailure.MALFORMED);
        }
        if (exp <= Instant.now().getEpochSecond()) {
            return Result.failed(ProofFailure.EXPIRED);
        }
        if (microcrystalSerial == null
                || !microcrystalSerial.equals(DeviceJson.textAt(payload, "microcrystalSerial"))) {
            return Result.failed(ProofFailure.WRONG_MICROCRYSTAL);
        }
        if (!expectedObserverType(principal).equals(DeviceJson.textAt(payload, "observerType"))
                || !expectedObserverRef(principal).equals(DeviceJson.textAt(payload, "observerRef"))) {
            // 控制端类型不符按账号不匹配处理；云台类型不符按云台不匹配处理。
            return Result.failed(expectedObserverType(principal).equals("gimbal")
                    ? ProofFailure.WRONG_GIMBAL : ProofFailure.WRONG_ACCOUNT);
        }
        if (principal.principalType() == PrincipalType.APP) {
            if (!principal.accountUuid().toString().equals(DeviceJson.textAt(payload, "accountId"))
                    || !principal.installationId().equals(DeviceJson.textAt(payload, "installationId"))) {
                return Result.failed(ProofFailure.WRONG_ACCOUNT);
            }
        } else if (!principal.gimbalUuid().toString().equals(DeviceJson.textAt(payload, "gimbalId"))) {
            return Result.failed(ProofFailure.WRONG_GIMBAL);
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

    private static String expectedObserverType(PrincipalContext principal) {
        return principal.principalType() == PrincipalType.APP ? "app_account" : "gimbal";
    }

    private static String expectedObserverRef(PrincipalContext principal) {
        return principal.principalType() == PrincipalType.APP
                ? principal.accountUuid() + ":" + principal.installationId()
                : principal.gimbalUuid().toString();
    }
}

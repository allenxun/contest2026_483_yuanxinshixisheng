package cn.yuanxin.mvp.web.devices.proof;

import java.util.UUID;

/**
 * 配对证明验证端口（DD §4.2；M2-A06/A07）。
 *
 * <p>证明必须绑定：目标云台 + 当前账号/安装实例 + 目的 + nonce + 有效期 +
 * 可验证签名；<b>不能仅凭 gimbalId</b>。真实设备签名算法/密钥预置尚未冻结，
 * 本端口是 B 自有 skeleton 接口，dev/test 由
 * {@link DevTestDoublePairingProofVerifier} 提供六种可区分输入；生产必须由
 * 真实实现装配，否则 B 自有 fail-closed 校验拒绝启动。</p>
 */
public interface PairingProofVerifier {

    Result verify(String proof, UUID expectedGimbalId, UUID accountId, String installationId);

    record Result(ProofFailure failure) {

        public static Result valid() {
            return new Result(null);
        }

        public static Result failed(ProofFailure failure) {
            return new Result(failure);
        }

        public boolean isValid() {
            return failure == null;
        }
    }
}

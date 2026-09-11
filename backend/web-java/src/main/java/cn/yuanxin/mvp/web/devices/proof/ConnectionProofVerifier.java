package cn.yuanxin.mvp.web.devices.proof;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

/**
 * 微晶连接证明验证端口（DD §4.2；M2-A04/A05）。
 *
 * <p>证明必须绑定控制端（当前 APP 账号+安装实例，或当前云台）+ 该微晶 +
 * 当前连接；<b>仅提交序列号一律拒绝</b>。控制端期望值由 {@link PrincipalContext}
 * 服务端派生，绝不取自请求体。真实微晶协议未冻结，dev/test 由
 * {@link DevTestDoubleConnectionProofVerifier} 提供六种可区分输入。</p>
 */
public interface ConnectionProofVerifier {

    Result verify(String proof, PrincipalContext principal, String microcrystalSerial);

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

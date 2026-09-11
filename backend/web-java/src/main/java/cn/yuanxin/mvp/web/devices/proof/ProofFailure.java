package cn.yuanxin.mvp.web.devices.proof;

/**
 * 证明验证失败原因（pairingProof / connectionProof 共用的可区分输入集合）。
 *
 * <p>映射约定（各控制器按契约 x-error-codes 决定最终 HTTP 码）：</p>
 * <ul>
 *   <li>{@code MISSING}/{@code MALFORMED} → 400 INVALID_INPUT（结构缺失/非法）；</li>
 *   <li>{@code UNSUPPORTED_VERSION} → 能力端点 A04 用 422 UNSUPPORTED_CONTRACT，
 *       A05/A06/A07 未声明该码，统一 403 CALLER_NOT_ALLOWED；</li>
 *   <li>其余（签名/过期/绑定错对象/nonce 重放）→ 403 CALLER_NOT_ALLOWED，
 *       除非查得该证明绑定的是"另一个微晶"（A05 按不可见处理 → 404）。</li>
 * </ul>
 * 这些是 B 自有 skeleton 协议的区分输入，<b>不代表设备真实协议已冻结</b>。
 */
public enum ProofFailure {
    MISSING,
    MALFORMED,
    UNSUPPORTED_VERSION,
    BAD_SIGNATURE,
    EXPIRED,
    WRONG_GIMBAL,
    WRONG_ACCOUNT,
    WRONG_MICROCRYSTAL,
    NONCE_REPLAY
}

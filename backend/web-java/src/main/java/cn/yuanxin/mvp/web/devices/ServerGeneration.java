package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;

/**
 * 服务端验证的观察代次（observation generation）唯一来源。
 *
 * <p>Oracle BLOCKER A：客户端自填的 {@code observationEpoch} 不能充当新旧权威——
 * 否则换一个 epoch 字符串即可用小 seq 回滚已接受的观察事实。观察顺序的唯一权威
 * 是<b>经服务端验证</b>的会话代次：</p>
 * <ul>
 *   <li>GIMBAL 主体：{@code credentialVersion}（每请求由 A 的
 *       PrincipalRevalidator 对 T03 复核）与 {@code sessionId}（服务端签发）组合；</li>
 *   <li>APP 主体：{@code sessionId}（服务端签发的登录会话）。</li>
 * </ul>
 *
 * <p>该值只从 {@link PrincipalContext} 派生，绝不读取请求体任何字段；同一
 * serverGeneration 内客户端不得更换 epoch，且 {@code observationSeq} 必须严格
 * 递增。真实代次推进（重新认证 / credential_version 轮换）才会开启新的基准。</p>
 */
final class ServerGeneration {

    private ServerGeneration() {
    }

    static String of(PrincipalContext principal) {
        return switch (principal.principalType()) {
            case GIMBAL -> "gimbal:" + principal.credentialVersion() + ":" + principal.sessionId();
            case APP -> "app:" + principal.sessionId();
        };
    }
}

package cn.yuanxin.mvp.web.care;

import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * 成员绑定人脸核验的 <b>dev/test 替身</b>（仅开发/测试；@Primary 覆盖
 * {@link FailClosedCareFaceVerifier}）。
 *
 * <p>与 {@code FaceProviderDouble} 不同，本替身<b>包含目标成员输入</b>：只有
 * 调用方传入的 {@code memberId} 与显式 {@link #bindMember(UUID) 绑定成员}一致时
 * 才返回 MATCHED；异成员返回 MISMATCH（异成员拒绝证据）；未绑定返回
 * CAPABILITY_UNAVAILABLE（未配置 ≠ 通过，fail-closed）。</p>
 */
@Component
@Profile({"dev", "test"})
@Primary
public class MemberBindingFaceDouble implements CareFaceVerifier {

    private volatile UUID boundMemberId;
    private volatile Outcome forcedOutcome;
    private volatile UUID lastRequestedMemberId;

    @Override
    public Outcome verifyOneToOne(String purpose, UUID memberId, byte[] candidate) {
        this.lastRequestedMemberId = memberId;
        Outcome forced = forcedOutcome;
        if (forced != null) {
            return forced;
        }
        UUID bound = boundMemberId;
        if (bound == null) {
            return Outcome.CAPABILITY_UNAVAILABLE;
        }
        return memberId != null && bound.equals(memberId) ? Outcome.MATCHED : Outcome.MISMATCH;
    }

    /** 绑定唯一可信目标成员。 */
    public void bindMember(UUID memberId) {
        this.boundMemberId = memberId;
    }

    /** 强制返回固定分类（优先于绑定判定）。 */
    public void forceOutcome(Outcome outcome) {
        this.forcedOutcome = outcome;
    }

    /** 清除绑定与强制分类（测试隔离）。 */
    public void reset() {
        this.boundMemberId = null;
        this.forcedOutcome = null;
        this.lastRequestedMemberId = null;
    }

    /** 最近一次请求传入的目标成员（供断言“确实传入方案成员”）。 */
    public UUID lastRequestedMemberId() {
        return lastRequestedMemberId;
    }
}

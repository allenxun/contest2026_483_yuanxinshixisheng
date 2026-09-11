package cn.yuanxin.mvp.web.care;

import org.springframework.beans.factory.annotation.Value;
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
 *
 * <p>活体 dev 运行时无法调用测试钩子，可用环境配置给出目标成员：
 * {@code APP_C_FACE_BOUND_MEMBER}（或属性 {@code app.testdouble.care-face.bound-member}）。
 * 空白→不绑定（fail-closed 不变）；合法 UUID→初始绑定；非法非空→启动即失败
 * （fail fast）。{@link #reset()} 恢复到初始环境绑定，故测试未配置该属性时行为
 * 与既有完全一致。<b>仅 dev/test 激活</b>（{@code @Profile}）：生产不注册本类，
 * 生产路径仍由 {@link FailClosedCareFaceVerifier} 恒 CAPABILITY_UNAVAILABLE。
 * 环境绑定是 E2E/活体联调便利，<b>不降低</b>异成员 MISMATCH 拒绝；真实提供方
 * 接入后应移除。</p>
 */
@Component
@Profile({"dev", "test"})
@Primary
public class MemberBindingFaceDouble implements CareFaceVerifier {

    private final UUID initialBoundMemberId;

    private volatile UUID boundMemberId;
    private volatile Outcome forcedOutcome;
    private volatile UUID lastRequestedMemberId;

    public MemberBindingFaceDouble(
            @Value("${APP_C_FACE_BOUND_MEMBER:${app.testdouble.care-face.bound-member:}}")
            String configuredMemberId) {
        this.initialBoundMemberId = parseConfiguredMember(configuredMemberId);
        this.boundMemberId = this.initialBoundMemberId;
    }

    private static UUID parseConfiguredMember(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return UUID.fromString(raw.trim());
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException(
                    "app.testdouble.care-face.bound-member must be a UUID or blank: " + raw, invalid);
        }
    }

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

    /** 恢复到初始环境绑定并清除强制分类（测试隔离）。 */
    public void reset() {
        this.boundMemberId = initialBoundMemberId;
        this.forcedOutcome = null;
        this.lastRequestedMemberId = null;
    }

    /** 最近一次请求传入的目标成员（供断言“确实传入方案成员”）。 */
    public UUID lastRequestedMemberId() {
        return lastRequestedMemberId;
    }
}

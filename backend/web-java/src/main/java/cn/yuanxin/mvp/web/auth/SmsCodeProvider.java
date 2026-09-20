package cn.yuanxin.mvp.web.auth;

import java.util.Optional;

/**
 * 短信验证码挑战端口（DD 4.1）。提供方负责验证码生命周期与风控；
 * 不泄露账号是否已存在。真实供应商未选定——替身仅 dev/test。
 */
public interface SmsCodeProvider {

    /** 发起挑战：返回 challengeId 与建议重试等待秒数。 */
    ChallengeOutcome issue(String phone, String purpose);

    /**
     * 验证 challengeId + code；成功返回服务端规范化的 login_subject（手机号）。
     * 失败返回 empty（不区分"错码"与"无挑战"，避免探测）。
     */
    Optional<String> verify(String challengeId, String code);

    record ChallengeOutcome(String challengeId, int retryAfterSeconds) {
    }
}

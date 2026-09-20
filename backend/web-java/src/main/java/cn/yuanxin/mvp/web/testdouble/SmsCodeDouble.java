package cn.yuanxin.mvp.web.testdouble;

import cn.yuanxin.mvp.web.auth.SmsCodeProvider;

import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 短信验证码测试替身（仅 dev/test）：固定 dev 验证码（默认 "123456"，属性
 * app.testdouble.sms.fixed-code 可改），挑战 5 分钟过期、一次性消费。
 * 真实供应商未选定（digest §6/§11）——绝不得对该替身做真实用户接入。
 */
public class SmsCodeDouble implements SmsCodeProvider {

    private record Challenge(String phone, String code, Instant expiresAt, boolean consumed) {
    }

    private final Map<String, Challenge> challenges = new ConcurrentHashMap<>();
    private final String fixedCode;
    private final SecureRandom random = new SecureRandom();

    public SmsCodeDouble(String fixedCode) {
        this.fixedCode = fixedCode;
    }

    @Override
    public ChallengeOutcome issue(String phone, String purpose) {
        String challengeId = UUID.randomUUID().toString().replace("-", "")
                + Long.toHexString(random.nextLong());
        challenges.put(challengeId, new Challenge(phone, fixedCode,
                Instant.now().plus(Duration.ofMinutes(5)), false));
        return new ChallengeOutcome(challengeId, 60);
    }

    @Override
    public Optional<String> verify(String challengeId, String code) {
        Challenge c = challenges.get(challengeId);
        if (c == null || c.consumed() || c.expiresAt().isBefore(Instant.now())
                || !c.code().equals(code)) {
            return Optional.empty();
        }
        challenges.put(challengeId, new Challenge(c.phone(), c.code(), c.expiresAt(), true));
        return Optional.of(c.phone());
    }
}

package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.care.CareFaceVerifier.Outcome;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * {@link MemberBindingFaceDouble} 纯单元测试（无 Spring 上下文）：
 * 环境配置目标成员绑定、未配置 fail-closed、非法配置 fail-fast、reset 语义。
 */
class MemberBindingFaceDoubleTest {

    private static final byte[] FACE = new byte[]{1, 2, 3};

    @Test
    @DisplayName("(a) 配置合法 UUID → 该成员 MATCHED、异成员 MISMATCH")
    void configuredMemberBinding() {
        UUID bound = UUID.randomUUID();
        MemberBindingFaceDouble verifier = new MemberBindingFaceDouble(bound.toString());
        assertEquals(Outcome.MATCHED, verifier.verifyOneToOne("admission", bound, FACE));
        assertEquals(Outcome.MISMATCH,
                verifier.verifyOneToOne("admission", UUID.randomUUID(), FACE));
        assertEquals(Outcome.MISMATCH, verifier.verifyOneToOne("revalidation", null, FACE));
    }

    @Test
    @DisplayName("(b) 配置空/空白/null → 未绑定 CAPABILITY_UNAVAILABLE；bind 后 MATCHED；reset 回退")
    void unboundThenBindThenReset() {
        for (String blank : new String[]{"", "   ", null}) {
            MemberBindingFaceDouble verifier = new MemberBindingFaceDouble(blank);
            UUID member = UUID.randomUUID();
            assertEquals(Outcome.CAPABILITY_UNAVAILABLE,
                    verifier.verifyOneToOne("admission", member, FACE), "blank=" + blank);
            verifier.bindMember(member);
            assertEquals(Outcome.MATCHED, verifier.verifyOneToOne("admission", member, FACE));
            verifier.reset();
            assertEquals(Outcome.CAPABILITY_UNAVAILABLE,
                    verifier.verifyOneToOne("admission", member, FACE), "reset blank=" + blank);
        }
    }

    @Test
    @DisplayName("(c) 配置非法非空串 → 构造抛 IllegalArgumentException（fail fast）")
    void invalidConfiguredMemberFailsFast() {
        assertThrows(IllegalArgumentException.class,
                () -> new MemberBindingFaceDouble("not-a-uuid"));
        assertThrows(IllegalArgumentException.class,
                () -> new MemberBindingFaceDouble("12345"));
    }

    @Test
    @DisplayName("(d) reset() 恢复初始环境绑定：配置 UUID 时 reset 后仍 MATCHED 该成员")
    void resetRestoresConfiguredBinding() {
        UUID bound = UUID.randomUUID();
        MemberBindingFaceDouble verifier = new MemberBindingFaceDouble(bound.toString());
        verifier.forceOutcome(Outcome.UNCERTAIN);
        assertEquals(Outcome.UNCERTAIN, verifier.verifyOneToOne("admission", bound, FACE));
        verifier.bindMember(UUID.randomUUID());
        verifier.reset();
        assertEquals(Outcome.MATCHED, verifier.verifyOneToOne("admission", bound, FACE));
        assertEquals(Outcome.MISMATCH,
                verifier.verifyOneToOne("admission", UUID.randomUUID(), FACE));
    }
}

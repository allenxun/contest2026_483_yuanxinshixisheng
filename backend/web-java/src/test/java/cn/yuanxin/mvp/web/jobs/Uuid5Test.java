package cn.yuanxin.mvp.web.jobs;

import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * UUIDv5 跨语言向量（contracts/decisions-notes.md §4：
 * samples/jobs/job-handoff-example.json 的 owner_id）。
 */
class Uuid5Test {

    @Test
    void fixedNamespaceVectorMatchesPython() {
        UUID got = Uuid5.uuid5(Uuid5.FIXED_NS,
                "system:echo:2f6a2b0e-3c1e-4d2b-9b57-1f4c3a5b6d78");
        assertEquals(UUID.fromString("b13b43dc-cfb1-5e89-8be2-72564704de79"), got);
    }

    @Test
    void identityNamespaceStyle() {
        // 稳定输入 → 稳定输出（同输入两侧一致；格式 "<ns>:<faceSubjectRef>"）
        UUID a = Uuid5.uuid5(Uuid5.FIXED_NS, "yuanxin-face:subject-1");
        UUID b = Uuid5.uuid5(Uuid5.FIXED_NS, "yuanxin-face:subject-1");
        UUID c = Uuid5.uuid5(Uuid5.FIXED_NS, "yuanxin-face:subject-2");
        assertEquals(a, b);
        assertEquals(5, a.version());
        assertEquals(2, a.variant());
        org.junit.jupiter.api.Assertions.assertNotEquals(a, c);
    }
}

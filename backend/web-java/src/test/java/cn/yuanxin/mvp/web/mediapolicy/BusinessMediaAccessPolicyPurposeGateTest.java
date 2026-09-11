package cn.yuanxin.mvp.web.mediapolicy;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.media.MediaObject;
import cn.yuanxin.mvp.web.media.MediaPurpose;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.verifyNoInteractions;

/**
 * 用途闸门单元测试：非 {@code assessment_result} 用途（含核验证据
 * {@code assessment_source} / 三类 face）必须在<b>任何 DB 查询之前</b>被拒绝，
 * 使核验证据图永不经业务 HTTP 读取。
 */
class BusinessMediaAccessPolicyPurposeGateTest {

    private static MediaObject media(MediaPurpose purpose) {
        return new MediaObject(UUID.randomUUID(), "mvp-a-test", "test/key", purpose,
                "available", "app", "ref", null, "image/png", 1L, "hash");
    }

    private static PrincipalContext app() {
        return new PrincipalContext(PrincipalType.APP, UUID.randomUUID(), "inst", null, 0, "s", "r");
    }

    @Test
    @DisplayName("非 assessment_result 用途全部拒绝且零 DB 交互；null purpose / null media 同样拒绝")
    void nonResultPurposesDeniedBeforeAnyQuery() {
        JdbcTemplate jdbc = Mockito.mock(JdbcTemplate.class);
        BusinessMediaAccessPolicy policy = new BusinessMediaAccessPolicy(jdbc, new ObjectMapper());

        for (MediaPurpose purpose : List.of(MediaPurpose.ASSESSMENT_SOURCE,
                MediaPurpose.GRANT_FACE, MediaPurpose.EXECUTION_FACE,
                MediaPurpose.REVALIDATION_FACE)) {
            assertFalse(policy.canAccess(app(), media(purpose)),
                    purpose.dbValue() + " 必须被拒绝");
        }
        assertFalse(policy.canAccess(app(), media(null)), "null purpose 必须被拒绝");
        assertFalse(policy.canAccess(app(), null), "null media 必须被拒绝");
        assertFalse(policy.canAccess(null, media(MediaPurpose.ASSESSMENT_SOURCE)),
                "null principal 必须被拒绝");

        verifyNoInteractions(jdbc);
    }
}

package cn.yuanxin.mvp.web.assessments;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * A01 app 级三图合计上限分支：用小上限（properties override）而非真实 32MiB
 * 触发 {@code AssessmentMultipartParser.checkTotalSize} → 413 UPLOAD_TOO_LARGE。
 * 独立 @TestPropertySource 使本类使用专属 Spring 上下文（共享同一临时库）。
 */
@TestPropertySource(properties = "app.assessments.max-request-bytes=16")
class AssessmentSizeLimitIT extends AssessmentTestSupport {

    @Test
    @DisplayName("A01 三图合计超配置上限 → 413 UPLOAD_TOO_LARGE，无 T05/T13 写")
    void totalSizeExceedsConfiguredLimit() throws Exception {
        GimbalFixture gimbal = createGimbal();
        // png() = 14 bytes × 3 = 42 > 16
        MvcResult r = postA01(gimbal.token(), "d-a01-size-" + UUID.randomUUID());
        assertEquals(413, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("UPLOAD_TOO_LARGE", error(r).path("code").asText());
        assertEquals(0, jdbc.queryForObject(
                "SELECT count(*) FROM skin_assessments WHERE gimbal_id = ?", Integer.class,
                gimbal.gimbalId()));
        assertEquals(0, jdbc.queryForObject(
                "SELECT count(*) FROM idempotency_requests WHERE principal_type='gimbal'"
                        + " AND principal_id = ?", Integer.class, gimbal.gimbalId().toString()));
    }
}

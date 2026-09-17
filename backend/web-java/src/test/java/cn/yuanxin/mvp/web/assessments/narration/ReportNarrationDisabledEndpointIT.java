package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalRevalidator;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.support.TestDatabase;
import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/**
 * {@code app.providers.mode=disabled} 下报告播报端点的依赖不可用语义（HTTP 级）：
 * 云台请求 503 DEPENDENCY_UNAVAILABLE 的 JSON 错误信封（即使带 {@code Accept: text/event-stream}），
 * 绝不回退替身/合成文案。
 *
 * <p>认证用测试自有 {@link InMemorySessionDouble}（{@code @Primary} 覆盖 disabled 占位
 * 会话提供方）与恒真 revalidator，因此可在能力关闭下仍能到达业务路径。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = "app.providers.mode=disabled")
class ReportNarrationDisabledEndpointIT {

    private static final ObjectMapper JSON = new ObjectMapper();

    private static final String VALID_PAYLOAD = """
            {"schema_version":1,
             "pores":{"score":61,"severity":"mild","name":"毛孔",
                      "regions":[{"region":"F","name":"额头","score":40,"severity":"ok"}]},
             "spots":{"score":55,"severity":"moderate","name":"斑点",
                      "regions":[{"region":"L","name":"左脸","score":35,"severity":"mild"}]},
             "surface_gloss":{"score":70,"severity":"none","name":"光泽",
                      "regions":[{"region":"R","name":"右脸","score":82,"severity":"good"}]}}
            """;

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", TestDatabase::url);
        registry.add("spring.datasource.username", TestDatabase::user);
        registry.add("spring.datasource.password", TestDatabase::password);
    }

    @TestConfiguration
    static class AuthConfig {
        @Bean
        @Primary
        SessionProvider testSessionProvider() {
            return new InMemorySessionDouble();
        }

        @Bean
        @Primary
        PrincipalRevalidator alwaysValidRevalidator() {
            return new PrincipalRevalidator(null) {
                @Override
                public boolean stillValid(AuthenticatedPrincipal p) {
                    return true;
                }
            };
        }
    }

    @Autowired
    MockMvc mockMvc;

    @Autowired
    SessionProvider sessionProvider;

    @Autowired
    JdbcTemplate jdbc;

    private record Seeded(UUID gimbalId, UUID taskId) {
    }

    /** 最小夹具：gimbal + 指针 + report_ready 任务（合法三项 payload）。 */
    private Seeded seedReportReadyTask() {
        String serial = "SN-RN-DIS-" + UUID.randomUUID().toString().substring(0, 8);
        UUID gimbalId = UUID.randomUUID();
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                + " VALUES (?, ?, ?, 3)", gimbalId, serial, "authref-" + serial);
        UUID t13 = UUID.randomUUID();
        jdbc.update("INSERT INTO idempotency_requests (id, principal_type, principal_id,"
                        + " operation, idempotency_key, payload_hash, status)"
                        + " VALUES (?, 'gimbal', ?, 'm3a01', ?, 'manual', 'succeeded')",
                t13, gimbalId.toString(), UUID.randomUUID().toString());
        UUID memberId = UUID.randomUUID();
        jdbc.update("INSERT INTO members (id) VALUES (?)", memberId);
        UUID reportId = UUID.randomUUID();
        UUID taskId = UUID.randomUUID();
        jdbc.update("INSERT INTO skin_assessments (id, gimbal_id, member_id, status,"
                        + " current_photo_version, processing_revision, photo_versions,"
                        + " identity_result, report_id, report_payload, report_photo_version,"
                        + " report_ready_at, source_request_id)"
                        + " VALUES (?, ?, ?, 'report_ready', 1, 1, '{}'::jsonb, '{}'::jsonb,"
                        + " ?, ?::jsonb, 1, now(), ?)",
                taskId, gimbalId, memberId, reportId, VALID_PAYLOAD, t13);
        jdbc.update("UPDATE gimbals SET current_assessment_id = ?,"
                + " current_assessment_revision = 1 WHERE id = ?", taskId, gimbalId);
        return new Seeded(gimbalId, taskId);
    }

    @Test
    @DisplayName("mode=disabled → 503 DEPENDENCY_UNAVAILABLE JSON（无下游、无合成文案）")
    void disabledCapabilityReturns503() throws Exception {
        Seeded seeded = seedReportReadyTask();
        String token = sessionProvider.createGimbalSession(seeded.gimbalId(), 1L).sessionToken();

        MvcResult result = mockMvc.perform(get(
                        "/api/v1/skin-assessment-tasks/{taskId}/report-narration-stream",
                        seeded.taskId())
                        .header("Authorization", "Bearer " + token)
                        .header("Accept", "text/event-stream"))
                .andReturn();

        assertThat(result.getResponse().getStatus()).isEqualTo(503);
        assertThat(result.getResponse().getContentType()).contains("application/json");
        JsonNode envelope = JSON.readTree(result.getResponse().getContentAsString());
        assertThat(envelope.path("error").path("code").asText()).isEqualTo("DEPENDENCY_UNAVAILABLE");
        assertThat(envelope.path("error").path("retryable").asBoolean()).isTrue();
    }
}

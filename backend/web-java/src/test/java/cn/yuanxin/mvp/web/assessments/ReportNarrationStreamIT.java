package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalRevalidator;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.support.TestDatabase;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * MOCK 测肤报告文案播报 SSE 端点端到端测试（真实 HTTP 服务器 RANDOM_PORT）：
 * <ul>
 *   <li>Test A：云台主体 + report_ready 任务 → 200 text/event-stream / no-store，
 *       事件顺序固定 {@code start → text_delta ×2 → done}，seq 1..4，data 含
 *       requestId/taskId/reportId，两段 delta 拼接为固定文案，恰一个成功终态；</li>
 *   <li>Test B：APP 主体 → 403 JSON 错误信封 {@code CALLER_NOT_ALLOWED}。</li>
 * </ul>
 *
 * <p>本 IT 为 RANDOM_PORT，不能复用 {@code AssessmentTestSupport} 的 MockMvc 夹具；
 * 故按最小夹具食谱在本地直接种入 PG 行（gimbal + 指针 + report_ready 任务），
 * 不修改任何共享支撑类。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Timeout(30)
class ReportNarrationStreamIT {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final HttpClient HTTP = HttpClient.newHttpClient();

    private static final String FULL_NARRATION =
            "本次完成额头、左脸、右脸和下巴四个区域的皮肤检测。"
                    + "额头61分，左脸39分，右脸67分，下巴45分。";

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
        PrincipalRevalidator alwaysValidRevalidator() {
            return new PrincipalRevalidator(null) {
                @Override
                public boolean stillValid(AuthenticatedPrincipal p) {
                    return true;
                }
            };
        }
    }

    @LocalServerPort
    int port;

    @Autowired
    SessionProvider sessionProvider;

    @Autowired
    JdbcTemplate jdbc;

    /** 单帧 SSE：event 名 + data 原文 + 原始 "event:/data:" 文本。 */
    private record Frame(String event, String data, String raw) {
    }

    private record Fixture(UUID gimbalId, UUID taskId, UUID reportId, String token) {
    }

    /** 最小夹具：gimbal 行 + 指针 + report_ready 任务（worker 独占列经 SQL 种入）。 */
    private Fixture seedReportReadyTask() {
        String serial = "SN-RN-" + UUID.randomUUID().toString().substring(0, 8);
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
                taskId, gimbalId, memberId, reportId,
                "{\"schema_version\":1,\"conclusion\":\"mock narration fixture\"}", t13);
        jdbc.update("UPDATE gimbals SET current_assessment_id = ?,"
                + " current_assessment_revision = 1 WHERE id = ?", taskId, gimbalId);

        String token = sessionProvider.createGimbalSession(gimbalId, 3L).sessionToken();
        return new Fixture(gimbalId, taskId, reportId, token);
    }

    private URI streamUri(UUID taskId) {
        return URI.create("http://127.0.0.1:" + port
                + "/api/v1/skin-assessment-tasks/" + taskId + "/report-narration-stream");
    }

    private static HttpRequest get(URI uri, String token) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(20))
                .header("Authorization", "Bearer " + token)
                .header("Accept", "text/event-stream")
                .GET()
                .build();
    }

    /** 增量读取原始 SSE，直到流结束（服务端关闭响应体）。 */
    private static List<Frame> readFrames(BufferedReader reader) throws Exception {
        List<Frame> frames = new ArrayList<>();
        String event = null;
        StringBuilder data = new StringBuilder();
        StringBuilder raw = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            raw.append(line).append('\n');
            if (line.isEmpty()) {
                if (event != null) {
                    frames.add(new Frame(event, data.toString(), raw.toString()));
                }
                event = null;
                data.setLength(0);
                raw.setLength(0);
            } else if (line.startsWith("event: ")) {
                event = line.substring("event: ".length());
            } else if (line.startsWith("data: ")) {
                data.append(line.substring("data: ".length()));
            }
        }
        return frames;
    }

    @Test
    @DisplayName("Test A 云台 + report_ready：200 text/event-stream，start→delta→delta→done，文案逐字节一致")
    void happyPathStreamsFixedNarration() throws Exception {
        Fixture fixture = seedReportReadyTask();

        HttpResponse<InputStream> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofInputStream());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue("Content-Type").orElse(""))
                .contains("text/event-stream");
        assertThat(response.headers().firstValue("Cache-Control").orElse(""))
                .contains("no-store");
        String requestIdHeader = response.headers().firstValue("X-Request-Id").orElse("");
        assertThat(requestIdHeader).isNotBlank();

        List<Frame> frames;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            frames = readFrames(reader);
        }

        // 原始帧（供人工对照）
        frames.forEach(f -> System.out.println("[narration-sse-frame]\n" + f.raw()));

        // 事件顺序固定，且恰有 4 帧（读至流结束 = 服务端已关闭响应体）。
        assertThat(frames).extracting(Frame::event)
                .containsExactly("start", "text_delta", "text_delta", "done");

        // seq 从 1 严格 +1。
        List<Integer> seqs = new ArrayList<>();
        for (Frame frame : frames) {
            JsonNode data = JSON.readTree(frame.data());
            assertThat(data.hasNonNull("requestId")).isTrue();
            assertThat(data.hasNonNull("taskId")).isTrue();
            assertThat(data.hasNonNull("reportId")).isTrue();
            assertThat(data.path("requestId").asText()).isEqualTo(requestIdHeader);
            assertThat(data.path("taskId").asText()).isEqualTo(fixture.taskId().toString());
            assertThat(data.path("reportId").asText()).isEqualTo(fixture.reportId().toString());
            seqs.add(data.path("seq").asInt());
        }
        assertThat(seqs).containsExactly(1, 2, 3, 4);

        // 两段 delta 拼接恰为固定文案（逐字节）。
        String delta1 = JSON.readTree(frames.get(1).data()).path("delta").asText();
        String delta2 = JSON.readTree(frames.get(2).data()).path("delta").asText();
        assertThat(delta1 + delta2).isEqualTo(FULL_NARRATION);
        assertThat(JSON.readTree(frames.get(0).data()).has("delta")).isFalse();
        assertThat(JSON.readTree(frames.get(3).data()).has("delta")).isFalse();

        // 恰一个终态且为成功（无 error）。
        assertThat(frames).noneMatch(f -> "error".equals(f.event()));
        assertThat(frames.stream()
                .filter(f -> "done".equals(f.event()) || "error".equals(f.event()))
                .count()).isEqualTo(1);
    }

    @Test
    @DisplayName("Test B APP 主体：403 预流 JSON 错误信封 CALLER_NOT_ALLOWED")
    void appPrincipalRejectedWithProblemJson() throws Exception {
        String appToken = sessionProvider
                .createAppSession(UUID.randomUUID(), "inst-rn-mock", 1L).accessToken();

        HttpResponse<String> response =
                HTTP.send(get(streamUri(UUID.randomUUID()), appToken),
                        HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(403);
        assertThat(response.headers().firstValue("Content-Type").orElse(""))
                .contains("application/json");
        JsonNode error = JSON.readTree(response.body()).path("error");
        assertThat(error.path("code").asText()).isEqualTo("CALLER_NOT_ALLOWED");
    }
}
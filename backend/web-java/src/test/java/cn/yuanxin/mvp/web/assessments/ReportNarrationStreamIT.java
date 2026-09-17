package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.assessments.narration.ReportNarrationAiStub;
import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalRevalidator;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.support.TestDatabase;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
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
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.function.Predicate;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 报告播报 SSE 端点端到端测试（真实 HTTP 服务器 RANDOM_PORT + 本地报告评估 AI stub）：
 * 真实下游转发后外部契约与原有断言全覆盖（200 text/event-stream / no-store、X-Request-Id 与每帧
 * requestId 相等、start→text_delta×N→done、seq 连续、恰一终态），并覆盖输入 fail-closed（422，
 * 无下游请求）、null/白名单与头契约、预流 503/504 JSON、流内单 error 终态、取消时关闭下游。
 *
 * <p>本 IT 为 RANDOM_PORT，不能复用 {@code AssessmentTestSupport} 的 MockMvc 夹具；
 * 故按最小夹具食谱在本地直接种入 PG 行（gimbal + 指针 + report_ready 任务），
 * 不修改任何共享支撑类。stub 使用明显假 key，绝不访问真实服务。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Timeout(30)
class ReportNarrationStreamIT {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final HttpClient HTTP = HttpClient.newHttpClient();
    private static final ReportNarrationAiStub STUB = new ReportNarrationAiStub();

    static {
        try {
            STUB.start();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** 合法 V3 形状三项评分。 */
    private static final String VALID_PAYLOAD = """
            {"schema_version":1,"conclusion":"ignored",
             "metrics":[{"name":"moisture","value":50,"unit":"%"}],
             "pores":{"score":61,"severity":"mild","name":"毛孔",
                      "regions":[{"region":"F","name":"额头","score":40,"severity":"ok"}]},
             "spots":{"score":55,"severity":"moderate","name":"斑点",
                      "regions":[{"region":"L","name":"左脸","score":35,"severity":"mild"}]},
             "surface_gloss":{"score":70,"severity":"none","name":"光泽",
                      "regions":[{"region":"R","name":"右脸","score":82,"severity":"good"}]}}
            """;

    /** 当前 Worker 真实形状：只有六键，不含三项评分。 */
    private static final String WORKER_PAYLOAD = """
            {"schema_version":1,"conclusion":"x",
             "metrics":[{"name":"moisture","value":50,"unit":"%"},
                        {"name":"oiliness","value":30,"unit":"%"},
                        {"name":"smoothness","value":70,"unit":"%"}],
             "description":"d","images":[],"model_info":{}}
            """;

    /** 含 null score/severity 与未知键的载荷（用于透传与白名单断言）。 */
    private static final String NULL_UNKNOWN_PAYLOAD = """
            {"schema_version":1,
             "pores":{"score":null,"severity":null,"name":"毛孔","debug":{"raw":[1,2]},
                      "regions":[{"region":"F","name":"额头","score":null,"severity":null,"extra":"x"}]},
             "spots":{"score":55,"severity":"moderate","name":"斑点",
                      "regions":[{"region":"L","name":"左脸","score":35,"severity":"mild"}]},
             "surface_gloss":{"score":70,"severity":"none","name":"光泽",
                      "regions":[{"region":"R","name":"右脸","score":82,"severity":"good"}]}}
            """;

    private static final String INVALID_SCORE_PAYLOAD = """
            {"schema_version":1,
             "pores":{"score":101,"severity":"mild","name":"毛孔",
                      "regions":[{"region":"F","name":"额头","score":40,"severity":"ok"}]},
             "spots":{"score":55,"severity":"moderate","name":"斑点",
                      "regions":[{"region":"L","name":"左脸","score":35,"severity":"mild"}]},
             "surface_gloss":{"score":70,"severity":"none","name":"光泽",
                      "regions":[{"region":"R","name":"右脸","score":82,"severity":"good"}]}}
            """;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", TestDatabase::url);
        registry.add("spring.datasource.username", TestDatabase::user);
        registry.add("spring.datasource.password", TestDatabase::password);
        registry.add("app.report-narration.base-url", STUB::baseUrl);
        registry.add("app.report-narration.api-key", () -> ReportNarrationAiStub.FAKE_API_KEY);
        registry.add("app.report-narration.connect-timeout-millis", () -> "2000");
        registry.add("app.report-narration.read-timeout-millis", () -> "1000");
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

    @AfterEach
    void resetStub() {
        STUB.reset();
    }

    /** 单帧 SSE：event 名 + data 原文 + 原始 "event:/data:" 文本。 */
    private record Frame(String event, String data, String raw) {
    }

    private record Fixture(UUID gimbalId, UUID taskId, UUID reportId, String token) {
    }

    /** 最小夹具：gimbal 行 + 指针 + report_ready 任务（worker 独占列经 SQL 种入）。 */
    private Fixture seedReportReadyTask(String reportPayload) {
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
                taskId, gimbalId, memberId, reportId, reportPayload, t13);
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

    /** 增量读取原始 SSE，直到出现满足 stop 的帧或流结束。 */
    private static List<Frame> readFrames(BufferedReader reader, Predicate<Frame> stop)
            throws IOException {
        List<Frame> frames = new ArrayList<>();
        String event = null;
        StringBuilder data = new StringBuilder();
        StringBuilder raw = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            raw.append(line).append('\n');
            if (line.isEmpty()) {
                if (event != null) {
                    Frame frame = new Frame(event, data.toString(), raw.toString());
                    frames.add(frame);
                    if (stop.test(frame)) {
                        return frames;
                    }
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

    private static List<Frame> readToTerminal(BufferedReader reader) throws IOException {
        return readFrames(reader, f -> "done".equals(f.event()) || "error".equals(f.event()));
    }

    private static List<Integer> seqs(List<Frame> frames) throws Exception {
        List<Integer> seqs = new ArrayList<>();
        for (Frame frame : frames) {
            seqs.add(JSON.readTree(frame.data()).path("seq").asInt());
        }
        return seqs;
    }

    // ------------------------------------------------------------------ tests

    @Test
    @DisplayName("A 成功流：200 text/event-stream/no-store，start→text_delta×N→done，seq 连续、恰一终态")
    void happyPathStreamsRealNarrationFromStub() throws Exception {
        Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
        STUB.script(List.of(
                ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.delta("本次完成"),
                ReportNarrationAiStub.delta("四项检测。"),
                ReportNarrationAiStub.completed("本次完成四项检测。")));

        HttpResponse<InputStream> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofInputStream());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue("Content-Type").orElse(""))
                .contains("text/event-stream");
        assertThat(response.headers().firstValue("Cache-Control").orElse("")).contains("no-store");
        String requestIdHeader = response.headers().firstValue("X-Request-Id").orElse("");
        assertThat(requestIdHeader).isNotBlank();

        List<Frame> frames;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            frames = readToTerminal(reader);
        }

        assertThat(frames).extracting(Frame::event)
                .containsExactly("start", "text_delta", "text_delta", "done");
        assertThat(seqs(frames)).containsExactly(1, 2, 3, 4);

        for (Frame frame : frames) {
            JsonNode data = JSON.readTree(frame.data());
            assertThat(data.hasNonNull("requestId")).isTrue();
            assertThat(data.hasNonNull("taskId")).isTrue();
            assertThat(data.hasNonNull("reportId")).isTrue();
            assertThat(data.path("requestId").asText()).isEqualTo(requestIdHeader);
            assertThat(data.path("taskId").asText()).isEqualTo(fixture.taskId().toString());
            assertThat(data.path("reportId").asText()).isEqualTo(fixture.reportId().toString());
        }

        // 首 delta 在 done 之前（帧顺序），delta 拼接 == stub 发出的完整文本。
        String delta1 = JSON.readTree(frames.get(1).data()).path("delta").asText();
        String delta2 = JSON.readTree(frames.get(2).data()).path("delta").asText();
        assertThat(delta1).isNotEmpty();
        assertThat(delta1 + delta2).isEqualTo("本次完成四项检测。");
        assertThat(JSON.readTree(frames.get(0).data()).has("delta")).isFalse();
        assertThat(JSON.readTree(frames.get(3).data()).has("delta")).isFalse();

        assertThat(frames).noneMatch(f -> "error".equals(f.event()));
        assertThat(frames.stream()
                .filter(f -> "done".equals(f.event()) || "error".equals(f.event()))
                .count()).isEqualTo(1);
    }

    @Test
    @DisplayName("B APP 主体：403 预流 JSON 错误信封 CALLER_NOT_ALLOWED（经 advice 渲染）")
    void appPrincipalRejectedWithProblemJson() throws Exception {
        String appToken = sessionProvider
                .createAppSession(UUID.randomUUID(), "inst-rn-live", 1L).accessToken();

        HttpResponse<String> response =
                HTTP.send(get(streamUri(UUID.randomUUID()), appToken),
                        HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(403);
        assertThat(response.headers().firstValue("Content-Type").orElse(""))
                .contains("application/json");
        JsonNode error = JSON.readTree(response.body()).path("error");
        assertThat(error.path("code").asText()).isEqualTo("CALLER_NOT_ALLOWED");
    }

    @Test
    @DisplayName("缺三项（当前 Worker 形状）→ 422 UNSUPPORTED_CONTRACT，下游请求计数 == 0")
    void missingThreeGroupsFailsClosedWithoutDownstream() throws Exception {
        Fixture fixture = seedReportReadyTask(WORKER_PAYLOAD);

        HttpResponse<String> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(422);
        assertThat(response.headers().firstValue("Content-Type").orElse(""))
                .contains("application/json");
        JsonNode error = JSON.readTree(response.body()).path("error");
        assertThat(error.path("code").asText()).isEqualTo("UNSUPPORTED_CONTRACT");
        assertThat(error.path("retryable").asBoolean()).isFalse();
        assertThat(STUB.requests()).isEmpty();
    }

    @Test
    @DisplayName("score 越界 → 422；details 只含结构性键路径")
    void invalidScoreFailsClosed() throws Exception {
        Fixture fixture = seedReportReadyTask(INVALID_SCORE_PAYLOAD);

        HttpResponse<String> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(422);
        JsonNode details = JSON.readTree(response.body()).path("error").path("details");
        assertThat(details.toString()).contains("pores.score");
        assertThat(details.toString()).doesNotContain("101");
        assertThat(STUB.requests()).isEmpty();
    }

    @Test
    @DisplayName("null score/severity 原样透传（JSON null，不是 0/省略）；未知键丢弃；body 恰好三键；头契约")
    void nullPassthroughWhitelistAndHeaders() throws Exception {
        Fixture fixture = seedReportReadyTask(NULL_UNKNOWN_PAYLOAD);
        STUB.script(List.of(
                ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.delta("x"),
                ReportNarrationAiStub.completed("x")));

        HttpResponse<InputStream> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofInputStream());
        assertThat(response.statusCode()).isEqualTo(200);
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            readToTerminal(reader);
        }

        ReportNarrationAiStub.Captured captured = STUB.lastRequest();
        assertThat(captured).isNotNull();
        // 头：必需头逐个存在且形状正确；绝不转发云台 Authorization/Cookie。
        assertThat(captured.header("X-Service-Name")).isEqualTo("medical-platform");
        assertThat(captured.header("X-API-Key")).isEqualTo(ReportNarrationAiStub.FAKE_API_KEY);
        assertThat(captured.header("X-Request-Id")).isNotBlank();
        assertThat(captured.header("Idempotency-Key")).isNotBlank();
        assertThat(captured.header("X-Protocol-Version")).isEqualTo("1.0");
        assertThat(captured.header("traceparent")).matches("^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$");
        assertThat(captured.header("Accept")).isEqualTo("text/event-stream");
        assertThat(captured.header("Content-Type")).isEqualTo("application/json");
        assertThat(captured.header("Authorization")).isNull();
        assertThat(captured.header("Cookie")).isNull();

        JsonNode body = JSON.readTree(captured.body());
        assertThat(fieldNames(body)).containsExactly("pores", "spots", "surface_gloss");
        assertThat(body.path("pores").path("score").isNull()).isTrue();
        assertThat(body.path("pores").path("severity").isNull()).isTrue();
        assertThat(body.path("pores").path("regions").get(0).path("score").isNull()).isTrue();
        for (String group : List.of("pores", "spots", "surface_gloss")) {
            assertThat(fieldNames(body.path(group)))
                    .containsExactly("score", "severity", "name", "regions");
        }
        // 未知键被丢弃：body 里绝不出现 debug/raw/extra。
        assertThat(captured.body()).doesNotContain("debug").doesNotContain("raw")
                .doesNotContain("extra");
    }

    @Test
    @DisplayName("下游预流非 2xx → 503 JSON（不是 SSE）")
    void downstreamPreStreamNon2xxMapsTo503() throws Exception {
        Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
        STUB.respond(503, "{\"code\":\"REPORT_SERVICE_UNAVAILABLE\"}");

        HttpResponse<String> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(503);
        assertThat(response.headers().firstValue("Content-Type").orElse(""))
                .contains("application/json");
        assertThat(JSON.readTree(response.body()).path("error").path("code").asText())
                .isEqualTo("DEPENDENCY_UNAVAILABLE");
    }

    @Test
    @DisplayName("下游预流超时 → 504 JSON（不是 SSE）")
    void downstreamPreStreamTimeoutMapsTo504() throws Exception {
        Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
        STUB.holdHeadersSilently(1800);

        HttpResponse<String> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(504);
        assertThat(JSON.readTree(response.body()).path("error").path("code").asText())
                .isEqualTo("DEPENDENCY_TIMEOUT");
    }

    @Test
    @DisplayName("下游 post-stream response.failed(TIMEOUT) → HTTP 200 + 恰一个 error 终态，无 done")
    void downstreamPostStreamFailedYieldsSingleError() throws Exception {
        Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
        STUB.script(List.of(
                ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.delta("a"),
                ReportNarrationAiStub.failed("AI_UPSTREAM_TIMEOUT")));

        HttpResponse<InputStream> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofInputStream());
        assertThat(response.statusCode()).isEqualTo(200);

        List<Frame> frames;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            frames = readToTerminal(reader);
        }
        assertThat(frames).extracting(Frame::event)
                .containsExactly("start", "text_delta", "error");
        assertThat(frames).noneMatch(f -> "done".equals(f.event()));
        assertThat(frames.stream().filter(f -> "error".equals(f.event())).count()).isEqualTo(1);
        JsonNode error = JSON.readTree(frames.get(2).data());
        assertThat(error.path("code").asText()).isEqualTo("DEPENDENCY_TIMEOUT");
        assertThat(error.path("message").asText()).doesNotContain("TIMEOUT");
    }

    @Test
    @DisplayName("零 delta + completed → error 终态（不是 done）")
    void zeroDeltaCompletedYieldsError() throws Exception {
        Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
        STUB.script(List.of(
                ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.completed("没有任何 delta")));

        List<Frame> frames = requestFrames(fixture);

        assertThat(frames).extracting(Frame::event).containsExactly("start", "error");
        assertThat(frames).noneMatch(f -> "done".equals(f.event()));
    }

    @Test
    @DisplayName("未知事件 / 重复终态 / 缺终态 → 恰一个 error 终态")
    void malformedDownstreamYieldsSingleError() throws Exception {
        for (List<String> script : List.of(
                List.of(ReportNarrationAiStub.accepted(), ReportNarrationAiStub.delta("a"),
                        "event: bogus\ndata: {}\n\n"),
                List.of(ReportNarrationAiStub.accepted(), ReportNarrationAiStub.delta("a"),
                        ReportNarrationAiStub.completed("a"), ReportNarrationAiStub.completed("a")),
                List.of(ReportNarrationAiStub.accepted(), ReportNarrationAiStub.delta("a")))) {
            Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
            STUB.script(script);
            List<Frame> frames = requestFrames(fixture);

            assertThat(frames).noneMatch(f -> "done".equals(f.event()));
            assertThat(frames.stream().filter(f -> "error".equals(f.event())).count())
                    .as("script=%s", script).isEqualTo(1);
        }
    }

    @Test
    @DisplayName("下游未发 accepted 直接 delta 即失败 → 外部只有恰一个 error 帧且 seq == 1")
    void downstreamWithoutAcceptedYieldsSingleErrorSeqOne() throws Exception {
        Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
        STUB.script(List.of(ReportNarrationAiStub.delta("a")));

        List<Frame> frames = requestFrames(fixture);

        assertThat(frames).extracting(Frame::event).containsExactly("error");
        assertThat(JSON.readTree(frames.get(0).data()).path("seq").asInt()).isEqualTo(1);
        assertThat(frames).noneMatch(f -> "start".equals(f.event()));
        assertThat(frames).noneMatch(f -> "done".equals(f.event()));
    }

    @Test
    @DisplayName("下游重复 accepted → 外部 error 终态且恰一个 start（绝不两个 start）")
    void duplicateAcceptedYieldsErrorInsteadOfTwoStarts() throws Exception {
        Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
        STUB.script(List.of(
                ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.delta("a"),
                ReportNarrationAiStub.completed("a")));

        List<Frame> frames = requestFrames(fixture);

        assertThat(frames).extracting(Frame::event).containsExactly("start", "error");
        assertThat(frames.stream().filter(f -> "start".equals(f.event())).count()).isEqualTo(1);
        assertThat(frames.stream().filter(f -> "error".equals(f.event())).count()).isEqualTo(1);
        assertThat(frames).noneMatch(f -> "done".equals(f.event()));
    }

    @Test
    @DisplayName("外部客户端断开 → 下游 AI 连接被关闭（stub 观测断开）")
    void clientDisconnectClosesDownstream() throws Exception {
        Fixture fixture = seedReportReadyTask(VALID_PAYLOAD);
        STUB.holdOpenSilently(List.of(ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.delta("a")), 100);

        HttpResponse<InputStream> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofInputStream());
        assertThat(response.statusCode()).isEqualTo(200);

        BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8));
        List<Frame> frames = readFrames(reader, f -> "text_delta".equals(f.event()));
        assertThat(frames).extracting(Frame::event).contains("text_delta");

        response.body().close(); // 外部客户端断开

        assertThat(STUB.awaitClientDisconnected(5000))
                .as("client disconnect must close the downstream AI connection").isTrue();
    }

    private List<Frame> requestFrames(Fixture fixture) throws Exception {
        HttpResponse<InputStream> response =
                HTTP.send(get(streamUri(fixture.taskId()), fixture.token()),
                        HttpResponse.BodyHandlers.ofInputStream());
        assertThat(response.statusCode()).isEqualTo(200);
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            return readToTerminal(reader);
        }
    }

    private static List<String> fieldNames(JsonNode node) {
        List<String> names = new ArrayList<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }
}

package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.assessments.AssessmentReadService;
import cn.yuanxin.mvp.web.assessments.AssessmentRepository;
import cn.yuanxin.mvp.web.assessments.dto.AssessmentTaskView;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * {@link ReportNarrationService} 门禁顺序、fail-closed 与 pump 帧纪律单测（无网络、无 PG）。
 */
class ReportNarrationServiceTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    private static final String VALID_PAYLOAD = """
            {"pores":{"score":61,"severity":"mild","name":"毛孔",
                      "regions":[{"region":"F","name":"额头","score":40,"severity":"ok"}]},
             "spots":{"score":55,"severity":"moderate","name":"斑点",
                      "regions":[{"region":"L","name":"左脸","score":35,"severity":"mild"}]},
             "surface_gloss":{"score":70,"severity":"none","name":"光泽",
                      "regions":[{"region":"R","name":"右脸","score":82,"severity":"good"}]}}
            """;

    private static final String WORKER_PAYLOAD = """
            {"schema_version":1,"conclusion":"x","metrics":[{"name":"moisture","value":50,"unit":"%"}],
             "description":"d","images":[],"model_info":{}}
            """;

    private AssessmentReadService readService;
    private AssessmentRepository repository;
    private RecordingClient client;
    private ReportNarrationService service;

    private final UUID taskId = UUID.randomUUID();
    private final UUID gimbalId = UUID.randomUUID();
    private final UUID reportId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        readService = mock(AssessmentReadService.class);
        repository = mock(AssessmentRepository.class);
        client = new RecordingClient();
        service = new ReportNarrationService(readService, repository, client, JSON);
    }

    private PrincipalContext gimbal() {
        return new PrincipalContext(PrincipalType.GIMBAL, null, null, gimbalId, 3L, "sess", "req-1");
    }

    private static AssessmentTaskView view(String reportId) {
        return new AssessmentTaskView("t", "report_ready", "1", List.of(), null, null,
                reportId, null);
    }

    private void givenReportRow(String payload) {
        when(repository.findByReportId(reportId)).thenReturn(Optional.of(
                new AssessmentRepository.ReportRow(taskId, gimbalId, UUID.randomUUID(),
                        "report_ready", payload, Instant.now())));
    }

    @Test
    @DisplayName("APP 主体：CALLER_NOT_ALLOWED，绝不读任务/打开下游")
    void appPrincipalRejectedBeforeDownstream() {
        PrincipalContext app = new PrincipalContext(PrincipalType.APP, UUID.randomUUID(), "inst",
                null, 0, "sess", "req-1");

        assertThatThrownBy(() -> service.openStream(app, taskId))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.CALLER_NOT_ALLOWED));
        verifyNoInteractions(readService, repository);
        assertThat(client.openCalls).isZero();
    }

    @Test
    @DisplayName("报告未就绪（reportId 空）→ 404 RESOURCE_NOT_VISIBLE，无下游")
    void reportNotReady() {
        when(readService.getTask(eq(taskId), any())).thenReturn(view(null));

        assertThatThrownBy(() -> service.openStream(gimbal(), taskId))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.RESOURCE_NOT_VISIBLE));
        assertThat(client.openCalls).isZero();
    }

    @Test
    @DisplayName("report_payload 行缺失/空白 → 404 RESOURCE_NOT_VISIBLE，无下游")
    void blankOrMissingPayload() {
        when(readService.getTask(eq(taskId), any())).thenReturn(view(reportId.toString()));
        when(repository.findByReportId(reportId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.openStream(gimbal(), taskId))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.RESOURCE_NOT_VISIBLE));
        assertThat(client.openCalls).isZero();
    }

    @Test
    @DisplayName("当前 Worker 形状（仅 metrics）→ 422 UNSUPPORTED_CONTRACT，下游请求数 == 0")
    void workerPayloadFailsClosedWithoutDownstream() {
        when(readService.getTask(eq(taskId), any())).thenReturn(view(reportId.toString()));
        givenReportRow(WORKER_PAYLOAD);

        assertThatThrownBy(() -> service.openStream(gimbal(), taskId))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> {
                    ApiException failure = (ApiException) thrown;
                    assertThat(failure.getCode()).isEqualTo(ErrorCode.UNSUPPORTED_CONTRACT);
                    assertThat(failure.getHttpStatus()).isEqualTo(422);
                    assertThat(failure.getDetails().get("missing"))
                            .isEqualTo(List.of("pores", "spots", "surface_gloss"));
                });
        assertThat(client.openCalls).isZero();
    }

    @Test
    @DisplayName("合法 payload → 以解析后的三项打开下游")
    void validPayloadOpensDownstream() {
        when(readService.getTask(eq(taskId), any())).thenReturn(view(reportId.toString()));
        givenReportRow(VALID_PAYLOAD);

        ReportNarrationService.Session session = service.openStream(gimbal(), taskId);

        assertThat(client.openCalls).isEqualTo(1);
        assertThat(client.lastScores.pores().name()).isEqualTo("毛孔");
        assertThat(session.requestId()).isEqualTo("req-1");
        assertThat(session.taskId()).isEqualTo(taskId.toString());
        assertThat(session.reportId()).isEqualTo(reportId.toString());
        session.close();
        assertThat(client.lastStream.closed).isTrue();
    }

    @Test
    @DisplayName("预流超时 → 504 DEPENDENCY_TIMEOUT；预流不可用 → 503")
    void preStreamFailuresMapped() {
        when(readService.getTask(eq(taskId), any())).thenReturn(view(reportId.toString()));
        givenReportRow(VALID_PAYLOAD);

        client.failure = new ReportNarrationException(ReportNarrationFailureKind.TIMEOUT, "timeout");
        assertThatThrownBy(() -> service.openStream(gimbal(), taskId))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_TIMEOUT));

        client.failure = new ReportNarrationException(ReportNarrationFailureKind.UNAVAILABLE, "down");
        assertThatThrownBy(() -> service.openStream(gimbal(), taskId))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    @Test
    @DisplayName("pump 成功：start→text_delta×N→done，seq 1..N+2，键序与字段正确；恰一个终态")
    void pumpSuccessFrames() throws Exception {
        FakeStream stream = new FakeStream(List.of(
                ReportNarrationEvent.accepted(),
                ReportNarrationEvent.delta("a"),
                ReportNarrationEvent.delta("b"),
                ReportNarrationEvent.completed("ab")));
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        service.pump(new ReportNarrationService.Session(stream, "req-1", taskId.toString(),
                reportId.toString()), out);

        List<String[]> frames = parseFrames(out.toString(StandardCharsets.UTF_8));
        assertThat(frames).extracting(f -> f[0])
                .containsExactly("start", "text_delta", "text_delta", "done");
        assertThat(seqs(frames)).containsExactly(1, 2, 3, 4);
        for (String[] frame : frames) {
            JsonNode data = JSON.readTree(frame[1]);
            assertThat(data.path("requestId").asText()).isEqualTo("req-1");
            assertThat(data.path("taskId").asText()).isEqualTo(taskId.toString());
            assertThat(data.path("reportId").asText()).isEqualTo(reportId.toString());
        }
        assertThat(JSON.readTree(frames.get(0)[1]).has("delta")).isFalse();
        assertThat(JSON.readTree(frames.get(1)[1]).path("delta").asText()).isEqualTo("a");
        assertThat(JSON.readTree(frames.get(3)[1]).has("delta")).isFalse();
    }

    @Test
    @DisplayName("pump 流内失败：恰一个 error 终态，code 按分类映射，无 done")
    void pumpFailureFrames() throws Exception {
        for (ReportNarrationFailureKind kind : List.of(
                ReportNarrationFailureKind.MALFORMED, ReportNarrationFailureKind.UNAVAILABLE)) {
            FakeStream stream = new FakeStream(
                    List.of(ReportNarrationEvent.accepted(), ReportNarrationEvent.delta("a")),
                    new ReportNarrationException(kind, "boom"));
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            service.pump(new ReportNarrationService.Session(stream, "req-1", taskId.toString(),
                    reportId.toString()), out);

            List<String[]> frames = parseFrames(out.toString(StandardCharsets.UTF_8));
            assertThat(frames).extracting(f -> f[0]).containsExactly("start", "text_delta", "error");
            JsonNode error = JSON.readTree(frames.get(2)[1]);
            assertThat(error.path("code").asText()).isEqualTo("DEPENDENCY_UNAVAILABLE");
            assertThat(error.path("message").asText())
                    .isEqualTo(ReportNarrationStreamController.ERROR_MESSAGE);
        }

        FakeStream timeout = new FakeStream(
                List.of(ReportNarrationEvent.accepted(), ReportNarrationEvent.delta("a")),
                new ReportNarrationException(ReportNarrationFailureKind.TIMEOUT, "slow"));
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        service.pump(new ReportNarrationService.Session(timeout, "req-1", taskId.toString(),
                reportId.toString()), out);
        List<String[]> frames = parseFrames(out.toString(StandardCharsets.UTF_8));
        assertThat(JSON.readTree(frames.get(2)[1]).path("code").asText())
                .isEqualTo("DEPENDENCY_TIMEOUT");
    }

    @Test
    @DisplayName("pump 下游 response.failed code 含 TIMEOUT → error DEPENDENCY_TIMEOUT，否则 UNAVAILABLE")
    void pumpFailedEventMapping() throws Exception {
        FakeStream timeout = new FakeStream(List.of(
                ReportNarrationEvent.delta("a"),
                ReportNarrationEvent.failed("AI_UPSTREAM_TIMEOUT")));
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        service.pump(new ReportNarrationService.Session(timeout, "r", taskId.toString(),
                reportId.toString()), out);
        assertThat(JSON.readTree(parseFrames(out.toString(StandardCharsets.UTF_8)).get(1)[1])
                .path("code").asText()).isEqualTo("DEPENDENCY_TIMEOUT");

        FakeStream unavailable = new FakeStream(List.of(
                ReportNarrationEvent.delta("a"),
                ReportNarrationEvent.failed("AI_INTERNAL")));
        out = new ByteArrayOutputStream();
        service.pump(new ReportNarrationService.Session(unavailable, "r", taskId.toString(),
                reportId.toString()), out);
        assertThat(JSON.readTree(parseFrames(out.toString(StandardCharsets.UTF_8)).get(1)[1])
                .path("code").asText()).isEqualTo("DEPENDENCY_UNAVAILABLE");
    }

    @Test
    @DisplayName("pump 循环无终态结束 → 防御性 error（绝不静默成功）")
    void pumpDefensiveError() throws Exception {
        FakeStream stream = new FakeStream(List.of());
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        service.pump(new ReportNarrationService.Session(stream, "r", taskId.toString(),
                reportId.toString()), out);
        List<String[]> frames = parseFrames(out.toString(StandardCharsets.UTF_8));
        assertThat(frames).extracting(f -> f[0]).containsExactly("error");
    }

    @Test
    @DisplayName("pump 客户端断开（写 IOException）→ 上抛，不写 error 终态")
    void pumpClientDisconnectPropagates() {
        FakeStream stream = new FakeStream(List.of(
                ReportNarrationEvent.accepted(), ReportNarrationEvent.delta("a"),
                ReportNarrationEvent.completed("a")));
        OutputStream failing = new OutputStream() {
            @Override
            public void write(int b) throws IOException {
                throw new IOException("client gone");
            }
        };

        assertThatThrownBy(() -> service.pump(new ReportNarrationService.Session(stream, "r",
                taskId.toString(), reportId.toString()), failing))
                .isInstanceOf(IOException.class);
    }

    // ---------------- helpers ----------------

    private static List<String[]> parseFrames(String raw) {
        List<String[]> frames = new java.util.ArrayList<>();
        String event = null;
        StringBuilder data = new StringBuilder();
        for (String line : raw.split("\n", -1)) {
            if (line.isEmpty()) {
                if (event != null) {
                    frames.add(new String[]{event, data.toString()});
                }
                event = null;
                data.setLength(0);
            } else if (line.startsWith("event: ")) {
                event = line.substring("event: ".length());
            } else if (line.startsWith("data: ")) {
                data.append(line.substring("data: ".length()));
            }
        }
        return frames;
    }

    private static List<Integer> seqs(List<String[]> frames) throws Exception {
        List<Integer> seqs = new java.util.ArrayList<>();
        for (String[] frame : frames) {
            seqs.add(JSON.readTree(frame[1]).path("seq").asInt());
        }
        return seqs;
    }

    /** 记录调用的 fake client。 */
    private static final class RecordingClient implements ReportNarrationClient {
        private int openCalls;
        private ReportNarrationScores lastScores;
        private FakeStream lastStream;
        private ReportNarrationException failure;

        @Override
        public ReportNarrationStream openStream(ReportNarrationScores scores) {
            openCalls++;
            lastScores = scores;
            if (failure != null) {
                throw failure;
            }
            lastStream = new FakeStream(List.of(ReportNarrationEvent.accepted()));
            return lastStream;
        }
    }

    /** 按脚本产出事件、可选在末尾抛异常的 fake stream。 */
    private static final class FakeStream implements ReportNarrationStream {
        private final Deque<ReportNarrationEvent> events = new ArrayDeque<>();
        private final ReportNarrationException failure;
        private boolean closed;

        FakeStream(List<ReportNarrationEvent> events) {
            this(events, null);
        }

        FakeStream(List<ReportNarrationEvent> events, ReportNarrationException failure) {
            events.forEach(this.events::add);
            this.failure = failure;
        }

        @Override
        public ReportNarrationEvent next() {
            if (!events.isEmpty()) {
                return events.poll();
            }
            if (failure != null) {
                throw failure;
            }
            return null;
        }

        @Override
        public void close() {
            closed = true;
        }
    }
}

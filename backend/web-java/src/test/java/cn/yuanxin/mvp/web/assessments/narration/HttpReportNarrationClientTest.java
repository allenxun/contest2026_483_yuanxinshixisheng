package cn.yuanxin.mvp.web.assessments.narration;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link HttpReportNarrationClient} 本地 stub 测试（SSE 流式）：出站逐字契约（含 body 恰好三键、
 * score/severity null 透传、绝不转发入站头）、失败分类、有界性与取消。
 */
class HttpReportNarrationClientTest {

    private static final String API_KEY = ReportNarrationAiStub.FAKE_API_KEY;
    private static final Pattern REQUEST_ID_PATTERN = Pattern.compile("^[A-Za-z0-9._:-]{8,128}$");
    private static final Pattern TRACEPARENT_PATTERN =
            Pattern.compile("^00-[0-9a-f]{32}-[0-9a-f]{16}-01$");

    private final ObjectMapper mapper = new ObjectMapper();
    private ReportNarrationAiStub stub;
    private HttpReportNarrationClient client;

    @BeforeEach
    void setUp() throws IOException {
        stub = new ReportNarrationAiStub();
        stub.start();
        client = new HttpReportNarrationClient(properties(stub.baseUrl(), 2000, 1000), mapper);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private static ReportNarrationProperties properties(String baseUrl, int connect, int read) {
        return new ReportNarrationProperties(baseUrl, API_KEY, connect, read);
    }

    private static ReportNarrationScores.ScoreGroup group(String name, BigDecimal score,
                                                          String severity, ReportNarrationScores.Region region) {
        return new ReportNarrationScores.ScoreGroup(score, severity, name, List.of(region));
    }

    private static ReportNarrationScores scores() {
        return new ReportNarrationScores(
                group("毛孔", new BigDecimal("61"), "mild",
                        new ReportNarrationScores.Region("F", "额头", new BigDecimal("40"), "ok")),
                group("斑点", new BigDecimal("55"), "moderate",
                        new ReportNarrationScores.Region("L", "左脸", new BigDecimal("35"), "mild")),
                group("光泽", new BigDecimal("70"), "none",
                        new ReportNarrationScores.Region("R", "右脸", new BigDecimal("82"), "good")));
    }

    private static List<ReportNarrationEvent> drain(ReportNarrationStream stream) {
        List<ReportNarrationEvent> events = new ArrayList<>();
        ReportNarrationEvent event;
        while ((event = stream.next()) != null) {
            events.add(event);
        }
        return events;
    }

    private static List<String> fieldNames(JsonNode node) {
        List<String> names = new ArrayList<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }

    private static long readerThreadCount() {
        return Thread.getAllStackTraces().keySet().stream()
                .filter(Thread::isAlive)
                .filter(thread -> "report-narration-sse-reader".equals(thread.getName()))
                .count();
    }

    private static void awaitReaderThreadsAtMost(long baseline, long timeoutMillis) {
        long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
        while (System.nanoTime() < deadline && readerThreadCount() > baseline) {
            try {
                Thread.sleep(20);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                break;
            }
        }
        assertThat(readerThreadCount()).isLessThanOrEqualTo(baseline);
    }

    private static long elapsedMillis(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000L;
    }

    @Test
    @DisplayName("成功：SSE 事件按序；出站 header/body 逐字契约对齐（:stream / text/event-stream / 恰好三键）")
    void successExactWireContract() throws Exception {
        ReportNarrationStream stream = client.openStream(scores());
        List<ReportNarrationEvent> events = drain(stream);
        assertThat(events).extracting(ReportNarrationEvent::type).contains(
                ReportNarrationEvent.Type.ACCEPTED, ReportNarrationEvent.Type.DELTA,
                ReportNarrationEvent.Type.COMPLETED);
        assertThat(events.get(events.size() - 1).spokenText()).isEqualTo("stub narration");

        ReportNarrationAiStub.Captured captured = stub.lastRequest();
        assertThat(captured).isNotNull();
        assertThat(captured.method()).isEqualTo("POST");
        assertThat(captured.path()).isEqualTo("/internal/v1/weijing/reports/assess:stream");
        assertThat(captured.header("X-Service-Name")).isEqualTo("medical-platform");
        assertThat(captured.header("X-API-Key")).isEqualTo(API_KEY);
        assertThat(captured.header("X-Protocol-Version")).isEqualTo("1.0");
        assertThat(captured.header("Accept")).isEqualTo("text/event-stream");
        assertThat(captured.header("Content-Type")).isEqualTo("application/json");
        assertThat(captured.header("X-Request-Id")).matches(REQUEST_ID_PATTERN);
        assertThat(captured.header("Idempotency-Key")).matches(REQUEST_ID_PATTERN);
        assertThat(captured.header("traceparent")).matches(TRACEPARENT_PATTERN);
        assertThat(captured.header("Last-Event-ID")).isNull();
        // 绝不转发云台的 Authorization/Cookie/任何入站头。
        assertThat(captured.header("Authorization")).isNull();
        assertThat(captured.header("Cookie")).isNull();

        JsonNode body = mapper.readTree(captured.body());
        assertThat(fieldNames(body)).containsExactly("pores", "spots", "surface_gloss");
        for (String groupName : List.of("pores", "spots", "surface_gloss")) {
            assertThat(fieldNames(body.path(groupName)))
                    .as("group %s whitelist", groupName)
                    .containsExactly("score", "severity", "name", "regions");
        }
        JsonNode region = body.path("pores").path("regions").get(0);
        assertThat(fieldNames(region)).containsExactly("region", "name", "score", "severity");
        assertThat(region.path("region").asText()).isEqualTo("F");
        assertThat(region.path("name").asText()).isEqualTo("额头");
    }

    @Test
    @DisplayName("score/severity 为 null：body 原样 JSON null（不是 0、不是省略）")
    void nullScoreAndSeverityPreserved() throws Exception {
        ReportNarrationScores scores = new ReportNarrationScores(
                group("毛孔", null, null, new ReportNarrationScores.Region("F", "额头", null, null)),
                scores().spots(), scores().surfaceGloss());

        drain(client.openStream(scores));

        JsonNode body = mapper.readTree(stub.lastRequest().body());
        assertThat(body.path("pores").path("score").isNull()).isTrue();
        assertThat(body.path("pores").path("severity").isNull()).isTrue();
        assertThat(body.path("pores").path("regions").get(0).path("score").isNull()).isTrue();
        assertThat(body.path("pores").path("score").asInt()).isEqualTo(0);
    }

    @Test
    @DisplayName("每次调用：X-Request-Id 与 Idempotency-Key 均为全新值")
    void freshRequestAndIdempotencyKeysPerCall() {
        drain(client.openStream(scores()));
        drain(client.openStream(scores()));

        assertThat(stub.requests()).hasSize(2);
        ReportNarrationAiStub.Captured first = stub.requests().get(0);
        ReportNarrationAiStub.Captured second = stub.requests().get(1);
        assertThat(first.header("X-Request-Id")).isNotEqualTo(second.header("X-Request-Id"));
        assertThat(first.header("Idempotency-Key")).isNotEqualTo(second.header("Idempotency-Key"));
    }

    @Test
    @DisplayName("预流非 2xx（problem+json）→ openStream 抛 UNAVAILABLE（携带状态/安全码）")
    void nonSuccessIsUnavailable() {
        stub.respond(503, "{\"code\":\"REPORT_SERVICE_UNAVAILABLE\",\"retryable\":true}");

        assertThatThrownBy(() -> client.openStream(scores()))
                .isInstanceOf(ReportNarrationException.class)
                .satisfies(thrown -> {
                    ReportNarrationException e = (ReportNarrationException) thrown;
                    assertThat(e.kind()).isEqualTo(ReportNarrationFailureKind.UNAVAILABLE);
                    assertThat(e.httpStatus()).isEqualTo(503);
                    assertThat(e.safeCode()).isEqualTo("REPORT_SERVICE_UNAVAILABLE");
                });
    }

    @Test
    @DisplayName("流内畸形（未知事件/缺终态/非 SSE）→ next() 抛 MALFORMED")
    void malformedStreamIsMalformed() {
        for (String body : List.of(
                "event: nope\ndata: {}\n\n",
                "event: response.delta\ndata: {\"delta\":\"only\"}\n\n",
                "not-sse-at-all")) {
            stub.respond(200, body);
            ReportNarrationStream stream = client.openStream(scores());
            assertThatThrownBy(() -> drain(stream))
                    .as("malformed stream: %s", body)
                    .isInstanceOf(ReportNarrationException.class)
                    .satisfies(thrown -> assertThat(((ReportNarrationException) thrown).kind())
                            .isEqualTo(ReportNarrationFailureKind.MALFORMED));
        }
    }

    @Test
    @DisplayName("下游永不发终态：读取超时 TIMEOUT、限期内返回、断开下游、线程收敛")
    void heldOpenDownstreamTimesOutAndReleases() {
        long baseline = readerThreadCount();
        stub.holdOpenSilently(List.of(ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.delta("A")), 100);
        ReportNarrationStream stream = client.openStream(scores());
        assertThat(stream.next().type()).isEqualTo(ReportNarrationEvent.Type.ACCEPTED);
        assertThat(stream.next().type()).isEqualTo(ReportNarrationEvent.Type.DELTA);

        long start = System.nanoTime();
        assertThatThrownBy(stream::next)
                .isInstanceOf(ReportNarrationException.class)
                .satisfies(thrown -> assertThat(((ReportNarrationException) thrown).kind())
                        .isEqualTo(ReportNarrationFailureKind.TIMEOUT));
        assertThat(elapsedMillis(start)).as("timeout near read-timeout (1s)").isBetween(700L, 3000L);

        assertThat(stub.awaitClientDisconnected(3000))
                .as("downstream exchange must be closed on timeout").isTrue();
        awaitReaderThreadsAtMost(baseline, 2000);
    }

    @Test
    @DisplayName("客户端 close()：下游交换被取消（stub 观测断开）、reader 线程收敛")
    void clientCloseCancelsDownstreamAndReleasesThreads() {
        long baseline = readerThreadCount();
        stub.holdOpenSilently(List.of(ReportNarrationAiStub.accepted(),
                ReportNarrationAiStub.delta("A")), 100);
        ReportNarrationStream stream = client.openStream(scores());
        assertThat(stream.next().type()).isEqualTo(ReportNarrationEvent.Type.ACCEPTED);
        assertThat(stream.next().type()).isEqualTo(ReportNarrationEvent.Type.DELTA);

        stream.close();

        assertThat(stub.awaitClientDisconnected(3000))
                .as("close() must actually cancel the downstream exchange").isTrue();
        awaitReaderThreadsAtMost(baseline, 2000);
    }

    @Test
    @DisplayName("预流超时：future 取消并收敛（下游观测断开），及时 TIMEOUT")
    void preStreamTimeoutCancelsAndConverges() {
        stub.holdHeadersSilently(2500);

        long start = System.nanoTime();
        assertThatThrownBy(() -> client.openStream(scores()))
                .isInstanceOf(ReportNarrationException.class)
                .satisfies(thrown -> assertThat(((ReportNarrationException) thrown).kind())
                        .isEqualTo(ReportNarrationFailureKind.TIMEOUT));
        assertThat(elapsedMillis(start)).isLessThan(3000L);

        assertThat(stub.awaitClientDisconnected(4000))
                .as("cancelled pre-stream exchange must not linger").isTrue();
    }

    @Test
    @DisplayName("非 2xx 慢 problem body：期限内返回、安全映射、code=null")
    void slowProblemBodyReturnsPromptlyWithNullCode() {
        stub.slowProblemBody(503, "{\"code\":\"REPORT_SLOW\",", 3000);

        long start = System.nanoTime();
        assertThatThrownBy(() -> client.openStream(scores()))
                .isInstanceOf(ReportNarrationException.class)
                .satisfies(thrown -> {
                    ReportNarrationException e = (ReportNarrationException) thrown;
                    assertThat(e.kind()).isEqualTo(ReportNarrationFailureKind.UNAVAILABLE);
                    assertThat(e.httpStatus()).isEqualTo(503);
                    assertThat(e.safeCode()).isNull();
                });
        assertThat(elapsedMillis(start))
                .as("problem body read must be deadline-bounded").isLessThan(3000L);
    }

    @Test
    @DisplayName("非 2xx 巨 body：仅读有界前缀、及时返回、code=null，不挂死")
    void hugeProblemBodyBoundedRead() {
        stub.respond(503, "{\"code\":\"" + "A".repeat(1_000_000) + "\"}");

        long start = System.nanoTime();
        assertThatThrownBy(() -> client.openStream(scores()))
                .isInstanceOf(ReportNarrationException.class)
                .satisfies(thrown -> {
                    ReportNarrationException e = (ReportNarrationException) thrown;
                    assertThat(e.kind()).isEqualTo(ReportNarrationFailureKind.UNAVAILABLE);
                    assertThat(e.safeCode()).isNull();
                });
        assertThat(elapsedMillis(start)).isLessThan(5000L);
    }

    @Test
    @DisplayName("恶意/超长 problem code：归一为 null 且绝不进日志")
    void maliciousProblemCodeSanitizedAndNotLogged() {
        String marker = "EVIL_USER_TEXT";
        stub.respond(503, "{\"code\":\"" + marker + "_" + "X".repeat(5000) + "\"}");

        Logger logger = (Logger) LoggerFactory.getLogger(HttpReportNarrationClient.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            assertThatThrownBy(() -> client.openStream(scores()))
                    .isInstanceOf(ReportNarrationException.class)
                    .satisfies(thrown -> assertThat(((ReportNarrationException) thrown).safeCode()).isNull());

            String logs = appender.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .collect(Collectors.joining("\n"));
            assertThat(logs).doesNotContain(marker).doesNotContain("XXXXX");
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }

    @Test
    @DisplayName("properties：缺失键只列键名；api-key 与 base-url 均脱敏；normalizedBaseUrl 仍返真实值")
    void propertiesRedactionAndDefaults() {
        ReportNarrationProperties empty = new ReportNarrationProperties("", "", null, null);
        assertThat(empty.missingRequiredKeys())
                .containsExactly("app.report-narration.base-url", "app.report-narration.api-key");
        assertThat(empty.connectTimeoutMillis()).isEqualTo(3000);
        assertThat(empty.readTimeoutMillis()).isEqualTo(30000);
        assertThat(empty.toString()).doesNotContain(API_KEY).contains("<absent>");

        ReportNarrationProperties configured = properties("http://127.0.0.1:1/", 3000, 10000);
        assertThat(configured.normalizedBaseUrl()).isEqualTo("http://127.0.0.1:1");
        // toString() 绝不含实际主机（base-url 虽非凭据，但会暴露内部主机）；仅客户端用真实值。
        assertThat(configured.toString()).doesNotContain(API_KEY)
                .doesNotContain("127.0.0.1").contains("<redacted>").contains("<configured>");
    }
}

package cn.yuanxin.mvp.web.gimbalai;

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
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link HttpGimbalAiClient} 本地 stub 测试（SSE 流式）：出站逐字契约、失败分类，以及
 * B1/B2 的有界性/取消/断开/洪泛/巨体与 I1 的码归一与日志纪律。
 */
class HttpGimbalAiClientTest {

    private static final String API_KEY = "TEST-API-KEY-PLACEHOLDER";
    private static final Pattern REQUEST_ID_PATTERN = Pattern.compile("^[A-Za-z0-9._:-]{8,128}$");
    private static final Pattern TRACEPARENT_PATTERN =
            Pattern.compile("^00-[0-9a-f]{32}-[0-9a-f]{16}-01$");

    private final ObjectMapper mapper = new ObjectMapper();
    private AiResponseStub stub;
    private HttpGimbalAiClient client;

    @BeforeEach
    void setUp() throws IOException {
        stub = new AiResponseStub();
        stub.start();
        client = new HttpGimbalAiClient(properties(stub.baseUrl(), 2000, 1000), mapper);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private static GimbalAiProperties properties(String baseUrl, int connect, int read) {
        return new GimbalAiProperties(baseUrl, API_KEY, connect, read);
    }

    private static List<GimbalAiEvent> drain(GimbalAiStream stream) {
        List<GimbalAiEvent> events = new ArrayList<>();
        GimbalAiEvent event;
        while ((event = stream.next()) != null) {
            events.add(event);
        }
        return events;
    }

    private static long readerThreadCount() {
        return Thread.getAllStackTraces().keySet().stream()
                .filter(Thread::isAlive)
                .filter(thread -> "gimbal-ai-sse-reader".equals(thread.getName()))
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
    @DisplayName("成功：SSE 事件按序；出站 header/body 逐字契约对齐（:stream / text/event-stream）")
    void successExactWireContract() throws Exception {
        GimbalAiStream stream = client.openStream("帮我看看皮肤");
        List<GimbalAiEvent> events = drain(stream);
        assertThat(events).extracting(GimbalAiEvent::type).contains(
                GimbalAiEvent.Type.ACCEPTED, GimbalAiEvent.Type.DELTA, GimbalAiEvent.Type.COMPLETED);
        assertThat(events.get(events.size() - 1).answerText()).isEqualTo("stub answer");

        AiResponseStub.Captured captured = stub.lastRequest();
        assertThat(captured).isNotNull();
        assertThat(captured.method()).isEqualTo("POST");
        assertThat(captured.path()).isEqualTo("/internal/v1/ai/responses:stream");
        assertThat(captured.header("X-Service-Name")).isEqualTo("medical-platform");
        assertThat(captured.header("X-API-Key")).isEqualTo(API_KEY);
        assertThat(captured.header("X-Protocol-Version")).isEqualTo("1.0");
        assertThat(captured.header("Accept")).isEqualTo("text/event-stream");
        assertThat(captured.header("Content-Type")).isEqualTo("application/json");
        assertThat(captured.header("X-Request-Id")).matches(REQUEST_ID_PATTERN);
        assertThat(captured.header("Idempotency-Key")).matches(REQUEST_ID_PATTERN);
        assertThat(captured.header("traceparent")).matches(TRACEPARENT_PATTERN);
        assertThat(captured.header("Last-Event-ID")).isNull();

        JsonNode body = mapper.readTree(captured.body());
        assertThat(body.path("protocol_version").asText()).isEqualTo("1.0");
        assertThat(body.path("use_case").asText()).isEqualTo("APP_AGENT_CONVERSATION");
        assertThat(body.path("request_id").asText()).isEqualTo(captured.header("X-Request-Id"));
        assertThat(body.path("input").path("text").asText()).isEqualTo("帮我看看皮肤");
        assertThat(captured.body()).doesNotContain("continuation_state");
    }

    @Test
    @DisplayName("每次调用：X-Request-Id 与 Idempotency-Key 均为全新值")
    void freshRequestAndIdempotencyKeysPerCall() {
        drain(client.openStream("first"));
        drain(client.openStream("second"));

        assertThat(stub.requests()).hasSize(2);
        AiResponseStub.Captured first = stub.requests().get(0);
        AiResponseStub.Captured second = stub.requests().get(1);
        assertThat(first.header("X-Request-Id")).isNotEqualTo(second.header("X-Request-Id"));
        assertThat(first.header("Idempotency-Key")).isNotEqualTo(second.header("Idempotency-Key"));
    }

    @Test
    @DisplayName("预流非 2xx（problem+json）→ openStream 抛 UNAVAILABLE（携带状态/安全码）")
    void nonSuccessIsUnavailable() {
        stub.respond(503, "{\"code\":\"AI_SERVICE_UNAVAILABLE\",\"retryable\":true}");

        assertThatThrownBy(() -> client.openStream("hi"))
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> {
                    GimbalAiException e = (GimbalAiException) thrown;
                    assertThat(e.kind()).isEqualTo(GimbalAiFailureKind.UNAVAILABLE);
                    assertThat(e.httpStatus()).isEqualTo(503);
                    assertThat(e.safeCode()).isEqualTo("AI_SERVICE_UNAVAILABLE");
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
            GimbalAiStream stream = client.openStream("hi");
            assertThatThrownBy(() -> drain(stream))
                    .as("malformed stream: %s", body)
                    .isInstanceOf(GimbalAiException.class)
                    .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                            .isEqualTo(GimbalAiFailureKind.MALFORMED));
        }
    }

    @Test
    @DisplayName("B1(a,c1) 下游永不发终态：读取超时 TIMEOUT、下限内返回、断开下游、线程收敛")
    void heldOpenDownstreamTimesOutAndReleases() {
        long baseline = readerThreadCount();
        stub.holdOpenSilently(List.of(AiResponseStub.accepted(), AiResponseStub.delta("A")), 100);
        GimbalAiStream stream = client.openStream("hi");
        assertThat(stream.next().type()).isEqualTo(GimbalAiEvent.Type.ACCEPTED);
        assertThat(stream.next().type()).isEqualTo(GimbalAiEvent.Type.DELTA);

        long start = System.nanoTime();
        assertThatThrownBy(stream::next)
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                        .isEqualTo(GimbalAiFailureKind.TIMEOUT));
        long elapsed = elapsedMillis(start);
        assertThat(elapsed).as("timeout must surface near read-timeout (1s)").isBetween(700L, 3000L);

        assertThat(stub.awaitClientDisconnected(3000))
                .as("downstream exchange must be closed on timeout").isTrue();
        awaitReaderThreadsAtMost(baseline, 2000);
    }

    @Test
    @DisplayName("B1(c2) 客户端 close()：下游交换被取消（stub 观测断开）、reader 线程收敛")
    void clientCloseCancelsDownstreamAndReleasesThreads() {
        long baseline = readerThreadCount();
        stub.holdOpenSilently(List.of(AiResponseStub.accepted(), AiResponseStub.delta("A")), 100);
        GimbalAiStream stream = client.openStream("hi");
        assertThat(stream.next().type()).isEqualTo(GimbalAiEvent.Type.ACCEPTED);
        assertThat(stream.next().type()).isEqualTo(GimbalAiEvent.Type.DELTA);

        stream.close();

        assertThat(stub.awaitClientDisconnected(3000))
                .as("close() must actually cancel the downstream exchange").isTrue();
        awaitReaderThreadsAtMost(baseline, 2000);
    }

    @Test
    @DisplayName("B1(c3) 洪泛小行（超队列容量）后到达终态：有界、不挂死")
    void floodedLinesReachTerminalWithoutHang() {
        List<String> frames = new ArrayList<>();
        for (int i = 0; i < 3000; i++) {
            frames.add(": keep-alive\n\n");
        }
        frames.add(AiResponseStub.completed("done"));
        stub.script(frames, 0);

        long start = System.nanoTime();
        List<GimbalAiEvent> events = drain(client.openStream("hi"));

        assertThat(events.get(events.size() - 1).answerText()).isEqualTo("done");
        assertThat(elapsedMillis(start)).isLessThan(10_000L);
    }

    @Test
    @DisplayName("B1(b,c3) 单行超 64KiB 上限 → 有界 fail-closed MALFORMED，不挂死")
    void oversizedLineFailsClosedMalformed() {
        stub.respond(200, "x".repeat(70 * 1024));
        GimbalAiStream stream = client.openStream("hi");

        long start = System.nanoTime();
        assertThatThrownBy(stream::next)
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                        .isEqualTo(GimbalAiFailureKind.MALFORMED));
        assertThat(elapsedMillis(start)).isLessThan(5000L);
    }

    @Test
    @DisplayName("B2(a) 预流超时：future 取消并收敛（下游观测断开），及时 TIMEOUT")
    void preStreamTimeoutCancelsAndConverges() {
        stub.holdHeadersSilently(2500);

        long start = System.nanoTime();
        assertThatThrownBy(() -> client.openStream("hi"))
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                        .isEqualTo(GimbalAiFailureKind.TIMEOUT));
        assertThat(elapsedMillis(start)).isLessThan(3000L);

        assertThat(stub.awaitClientDisconnected(4000))
                .as("cancelled pre-stream exchange must not linger").isTrue();
    }

    @Test
    @DisplayName("B2(b1) 非 2xx 慢 problem body：期限内返回、安全映射、code=null")
    void slowProblemBodyReturnsPromptlyWithNullCode() {
        stub.slowProblemBody(503, "{\"code\":\"AI_SLOW\",", 3000);

        long start = System.nanoTime();
        assertThatThrownBy(() -> client.openStream("hi"))
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> {
                    GimbalAiException e = (GimbalAiException) thrown;
                    assertThat(e.kind()).isEqualTo(GimbalAiFailureKind.UNAVAILABLE);
                    assertThat(e.httpStatus()).isEqualTo(503);
                    assertThat(e.safeCode()).isNull();
                });
        assertThat(elapsedMillis(start))
                .as("problem body read must be deadline-bounded").isLessThan(3000L);
    }

    @Test
    @DisplayName("B2(b2) 非 2xx 巨 body：仅读有界前缀、及时返回、code=null，不挂死")
    void hugeProblemBodyBoundedRead() {
        stub.respond(503, "{\"code\":\"" + "A".repeat(1_000_000) + "\"}");

        long start = System.nanoTime();
        assertThatThrownBy(() -> client.openStream("hi"))
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> {
                    GimbalAiException e = (GimbalAiException) thrown;
                    assertThat(e.kind()).isEqualTo(GimbalAiFailureKind.UNAVAILABLE);
                    assertThat(e.safeCode()).isNull();
                });
        assertThat(elapsedMillis(start)).isLessThan(5000L);
    }

    @Test
    @DisplayName("I1 恶意/超长 problem code：归一为 null 且绝不进日志")
    void maliciousProblemCodeSanitizedAndNotLogged() {
        String marker = "EVIL_USER_TEXT";
        stub.respond(503, "{\"code\":\"" + marker + "_" + "X".repeat(5000) + "\"}");

        Logger logger = (Logger) LoggerFactory.getLogger(HttpGimbalAiClient.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            assertThatThrownBy(() -> client.openStream("hi"))
                    .isInstanceOf(GimbalAiException.class)
                    .satisfies(thrown -> assertThat(((GimbalAiException) thrown).safeCode()).isNull());

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
    @DisplayName("properties：缺失键只列键名，api-key 在 toString 中脱敏")
    void propertiesRedaction() {
        GimbalAiProperties empty = new GimbalAiProperties("", "", null, null);
        assertThat(empty.missingRequiredKeys())
                .containsExactly("app.gimbal-ai.base-url", "app.gimbal-ai.api-key");
        assertThat(empty.connectTimeoutMillis()).isEqualTo(3000);
        assertThat(empty.readTimeoutMillis()).isEqualTo(10000);
        assertThat(empty.toString()).doesNotContain(API_KEY).contains("<absent>");

        GimbalAiProperties configured = properties("http://127.0.0.1:1/", 3000, 10000);
        assertThat(configured.normalizedBaseUrl()).isEqualTo("http://127.0.0.1:1");
        assertThat(configured.toString()).doesNotContain(API_KEY).contains("<redacted>");
    }
}

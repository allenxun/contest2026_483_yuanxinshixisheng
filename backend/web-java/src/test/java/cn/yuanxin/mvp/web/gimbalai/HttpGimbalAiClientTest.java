package cn.yuanxin.mvp.web.gimbalai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link HttpGimbalAiClient} 本地 stub 测试（SSE 流式）：锁定出站 header/body 逐字对齐、
 * 预流非 2xx / 预流超时 / 流内畸形 / 流内读取超时的失败分类（绝不成功、绝不回退一次性）。
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
    @DisplayName("预流非 2xx（problem+json）→ openStream 抛 UNAVAILABLE（携带状态/码）")
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
    @DisplayName("流内畸形（未知事件/缺终态）→ next() 抛 MALFORMED")
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
    @DisplayName("流内读取超时 → TIMEOUT")
    void readTimeoutIsTimeout() {
        stub.holdConnectionSilently(2000);
        GimbalAiStream stream = client.openStream("hi");

        assertThatThrownBy(stream::next)
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                        .isEqualTo(GimbalAiFailureKind.TIMEOUT));
    }

    @Test
    @DisplayName("预流（到首响应头）超时 → TIMEOUT")
    void preStreamTimeoutIsTimeout() {
        stub.holdHeadersSilently(2000);

        assertThatThrownBy(() -> client.openStream("hi"))
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                        .isEqualTo(GimbalAiFailureKind.TIMEOUT));
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

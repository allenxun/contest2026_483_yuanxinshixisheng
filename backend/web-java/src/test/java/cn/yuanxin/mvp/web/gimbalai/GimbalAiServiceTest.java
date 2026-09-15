package cn.yuanxin.mvp.web.gimbalai;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link GimbalAiService} 流式单元测试（无网络）：APP 拒绝且零下游、事件白名单重编码、
 * 流内失败恰一个 failed 终态（安全码/文案）、客户端断开上抛且不写合成答案。
 */
class GimbalAiServiceTest {

    private final ObjectMapper mapper = new ObjectMapper();
    private final List<String> downstreamOpenCalls = new ArrayList<>();

    private static final class FakeStream implements GimbalAiStream {
        private final Deque<Object> items = new ArrayDeque<>();
        private boolean closed;

        FakeStream(Object... eventsOrFailures) {
            for (Object item : eventsOrFailures) {
                items.add(item);
            }
        }

        @Override
        public GimbalAiEvent next() {
            Object item = items.poll();
            if (item == null) {
                return null;
            }
            if (item instanceof RuntimeException failure) {
                throw failure;
            }
            return (GimbalAiEvent) item;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    private GimbalAiService service(GimbalAiClient client) {
        return new GimbalAiService(client, mapper);
    }

    private static PrincipalContext gimbalPrincipal() {
        return PrincipalContext.forGimbal(
                AuthenticatedPrincipal.gimbal(UUID.randomUUID(), 1L, "sess"), "req-1");
    }

    private static PrincipalContext appPrincipal() {
        return PrincipalContext.forApp(
                AuthenticatedPrincipal.app(UUID.randomUUID(), "inst", "sess", 1L), "req-1");
    }

    private static List<String[]> parseExternalSse(String text) {
        List<String[]> events = new ArrayList<>();
        String event = null;
        StringBuilder data = new StringBuilder();
        for (String line : text.split("\n", -1)) {
            if (line.isEmpty()) {
                if (event != null) {
                    events.add(new String[]{event, data.toString()});
                }
                event = null;
                data.setLength(0);
            } else if (line.startsWith("event: ")) {
                event = line.substring("event: ".length());
            } else if (line.startsWith("data: ")) {
                data.append(line.substring("data: ".length()));
            }
        }
        return events;
    }

    @Test
    @DisplayName("APP 主体 → 403 CALLER_NOT_ALLOWED，且绝不打开下游")
    void appForbiddenWithoutDownstreamOpen() {
        GimbalAiClient spy = text -> {
            downstreamOpenCalls.add(text);
            return new FakeStream();
        };
        assertThatThrownBy(() -> service(spy).openStream(appPrincipal(), "hi"))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.CALLER_NOT_ALLOWED));
        assertThat(downstreamOpenCalls).isEmpty();
    }

    @Test
    @DisplayName("pump：白名单重编码 accepted/delta/completed，恰一个终态，completed.answerText 权威")
    void pumpReEncodesWhitelistEvents() throws Exception {
        FakeStream stream = new FakeStream(
                GimbalAiEvent.accepted(),
                GimbalAiEvent.delta("Hello "),
                GimbalAiEvent.delta("world"),
                GimbalAiEvent.completed("Hello world"));
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        service(text -> stream).pump(stream, out);

        List<String[]> events = parseExternalSse(out.toString(StandardCharsets.UTF_8));
        assertThat(events).extracting(e -> e[0]).containsExactly(
                "response.accepted", "response.delta", "response.delta", "response.completed");
        assertThat(mapper.readTree(events.get(1)[1]).path("delta").asText()).isEqualTo("Hello ");
        assertThat(mapper.readTree(events.get(3)[1]).path("answerText").asText())
                .isEqualTo("Hello world");
    }

    @Test
    @DisplayName("pump：流内畸形（MALFORMED）→ 恰一个 failed 终态（DEPENDENCY_UNAVAILABLE），无 completed")
    void pumpMalformedYieldsSingleFailedTerminal() throws Exception {
        FakeStream stream = new FakeStream(
                GimbalAiEvent.delta("partial"),
                new GimbalAiException(GimbalAiFailureKind.MALFORMED, "boom"));
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        service(text -> stream).pump(stream, out);

        List<String[]> events = parseExternalSse(out.toString(StandardCharsets.UTF_8));
        assertThat(events).extracting(e -> e[0]).containsExactly("response.delta", "response.failed");
        JsonNode failed = mapper.readTree(events.get(1)[1]);
        assertThat(failed.path("code").asText()).isEqualTo("DEPENDENCY_UNAVAILABLE");
        assertThat(failed.path("message").asText()).doesNotContain("boom");
    }

    @Test
    @DisplayName("pump：流内读取超时（TIMEOUT）→ 恰一个 failed 终态（DEPENDENCY_TIMEOUT）")
    void pumpTimeoutYieldsTimeoutTerminal() throws Exception {
        FakeStream stream = new FakeStream(
                new GimbalAiException(GimbalAiFailureKind.TIMEOUT, "slow"));
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        service(text -> stream).pump(stream, out);

        List<String[]> events = parseExternalSse(out.toString(StandardCharsets.UTF_8));
        assertThat(events).extracting(e -> e[0]).containsExactly("response.failed");
        assertThat(mapper.readTree(events.get(0)[1]).path("code").asText())
                .isEqualTo("DEPENDENCY_TIMEOUT");
    }

    @Test
    @DisplayName("pump：下游 failed 事件 → 恰一个 failed 终态（安全码/文案，无下游原文）")
    void pumpFailedEventYieldsFailedTerminal() throws Exception {
        FakeStream stream = new FakeStream(GimbalAiEvent.failed("AI_UPSTREAM_TIMEOUT"));
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        service(text -> stream).pump(stream, out);

        List<String[]> events = parseExternalSse(out.toString(StandardCharsets.UTF_8));
        assertThat(events).extracting(e -> e[0]).containsExactly("response.failed");
        JsonNode failed = mapper.readTree(events.get(0)[1]);
        assertThat(failed.path("code").asText()).isEqualTo("DEPENDENCY_TIMEOUT");
        assertThat(out.toString(StandardCharsets.UTF_8)).doesNotContain("AI_UPSTREAM_TIMEOUT");
    }

    @Test
    @DisplayName("客户端断开（写 IOException）→ 上抛、不写合成答案，且 finally 关闭下游")
    void clientDisconnectPropagatesAndClosesDownstream() {
        FakeStream stream = new FakeStream(GimbalAiEvent.delta("x"), GimbalAiEvent.completed("x"));
        GimbalAiService service = service(text -> stream);
        OutputStream failing = new OutputStream() {
            @Override
            public void write(int b) throws IOException {
                throw new IOException("client gone");
            }
        };
        StreamingResponseBody body = out -> {
            try {
                service.pump(stream, out);
            } finally {
                stream.close();
            }
        };

        assertThatThrownBy(() -> body.writeTo(failing)).isInstanceOf(IOException.class);
        assertThat(stream.closed).isTrue();
    }

    @Test
    @DisplayName("disabled 占位 → openStream 抛 503 DEPENDENCY_UNAVAILABLE（无下游），绝不合成答案")
    void disabledPlaceholderYieldsDependencyUnavailable() {
        MockEnvironment env = new MockEnvironment().withProperty("app.providers.mode", "disabled");
        GimbalAiClient disabled = GimbalAiProvidersConfig.createClient(
                new GimbalAiProperties("", "", null, null), env, mapper);

        assertThatThrownBy(() -> service(disabled).openStream(gimbalPrincipal(), "hi"))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    @Test
    @DisplayName("预流失败（openStream 抛 GimbalAiException）→ ApiException 503/504（JSON problem 语义）")
    void preStreamFailureMapsToDependencyProblem() {
        for (var entry : List.of(
                java.util.Map.entry(GimbalAiFailureKind.MALFORMED, ErrorCode.DEPENDENCY_UNAVAILABLE),
                java.util.Map.entry(GimbalAiFailureKind.UNAVAILABLE, ErrorCode.DEPENDENCY_UNAVAILABLE),
                java.util.Map.entry(GimbalAiFailureKind.TIMEOUT, ErrorCode.DEPENDENCY_TIMEOUT))) {
            GimbalAiClient failing = text -> {
                throw new GimbalAiException(entry.getKey(), "safe message");
            };
            assertThatThrownBy(() -> service(failing).openStream(gimbalPrincipal(), "hi"))
                    .as("kind=%s", entry.getKey())
                    .isInstanceOf(ApiException.class)
                    .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                            .isEqualTo(entry.getValue()));
        }
    }
}

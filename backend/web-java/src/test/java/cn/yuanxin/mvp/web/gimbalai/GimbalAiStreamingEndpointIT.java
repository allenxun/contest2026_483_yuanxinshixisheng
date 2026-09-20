package cn.yuanxin.mvp.web.gimbalai;

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
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 云台 AI 文本透传端到端<b>流式</b>测试（真实 HTTP 服务器 RANDOM_PORT + 本地下游 SSE stub）：
 * 外部为 {@code text/event-stream}，delta 在 completed 之前可观测（绝不缓冲），
 * 流内失败恰一个 {@code failed} 终态（无合成答案、无下游原文）。
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Timeout(30)
class GimbalAiStreamingEndpointIT {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final HttpClient HTTP = HttpClient.newHttpClient();
    private static final AiResponseStub STUB = new AiResponseStub();

    static {
        try {
            STUB.start();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", TestDatabase::url);
        registry.add("spring.datasource.username", TestDatabase::user);
        registry.add("spring.datasource.password", TestDatabase::password);
        registry.add("app.gimbal-ai.base-url", STUB::baseUrl);
        registry.add("app.gimbal-ai.api-key", () -> "TEST-API-KEY-PLACEHOLDER");
        registry.add("app.gimbal-ai.connect-timeout-millis", () -> "2000");
        registry.add("app.gimbal-ai.read-timeout-millis", () -> "1000");
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

    @AfterEach
    void resetStub() {
        STUB.releaseHeld();
        STUB.reset();
    }

    private String gimbalToken() {
        return sessionProvider.createGimbalSession(UUID.randomUUID(), 1L).sessionToken();
    }

    private HttpResponse<InputStream> postStreaming(String token, String body) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/api/v1/gimbal-ai/messages"))
                .timeout(Duration.ofSeconds(20))
                .header("Authorization", "Bearer " + token)
                .header("Content-Type", "application/json")
                .header("Accept", "text/event-stream")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        return HTTP.send(request, HttpResponse.BodyHandlers.ofInputStream());
    }

    /** 读取外部 SSE，直到出现满足 stop 的事件（返回含该事件在内的事件列表）。 */
    private static List<String[]> readEvents(BufferedReader reader, Predicate<String[]> stop)
            throws IOException {
        List<String[]> events = new ArrayList<>();
        String event = null;
        StringBuilder data = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            if (line.isEmpty()) {
                if (event != null) {
                    String[] parsed = {event, data.toString()};
                    events.add(parsed);
                    event = null;
                    data.setLength(0);
                    if (stop.test(parsed)) {
                        return events;
                    }
                } else {
                    data.setLength(0);
                }
                continue;
            }
            if (line.startsWith("event: ")) {
                event = line.substring("event: ".length());
            } else if (line.startsWith("data: ")) {
                data.append(line.substring("data: ".length()));
            }
        }
        return events;
    }

    @Test
    @DisplayName("流式成功：delta 在 completed 之前可观测（held completed），completed.answerText 权威")
    void deltasObservableBeforeCompleted() throws Exception {
        STUB.scriptHeld(List.of(AiResponseStub.accepted(), AiResponseStub.delta("AB")),
                AiResponseStub.completed("AB"));

        HttpResponse<InputStream> response = postStreaming(gimbalToken(), "{\"text\":\"hi\"}");
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue("Content-Type").orElse(""))
                .contains("text/event-stream");

        BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8));
        List<String[]> beforeCompleted = readEvents(reader, e -> "response.delta".equals(e[0]));
        assertThat(beforeCompleted).extracting(e -> e[0]).contains("response.accepted", "response.delta");
        assertThat(STUB.heldPending())
                .as("completed must not have been produced downstream yet").isTrue();

        STUB.releaseHeld();
        List<String[]> after = readEvents(reader, e -> "response.completed".equals(e[0]));
        assertThat(after).extracting(e -> e[0]).contains("response.completed");
        JsonNode completed = JSON.readTree(after.get(after.size() - 1)[1]);
        assertThat(completed.path("answerText").asText()).isEqualTo("AB");
        // 外部只有白名单数据；不得出现 SuccessEnvelope 形状。
        assertThat(after.stream().noneMatch(e -> e[1].contains("requestId"))).isTrue();
    }

    @Test
    @DisplayName("流内畸形（未知事件）→ HTTP 200 + 恰一个 failed 终态，无 completed/合成答案")
    void malformedDownstreamYieldsSingleFailedTerminal() throws Exception {
        STUB.script(List.of(
                AiResponseStub.accepted(),
                AiResponseStub.delta("A"),
                "event: bogus\ndata: {}\n\n"), 0);

        HttpResponse<InputStream> response = postStreaming(gimbalToken(), "{\"text\":\"hi\"}");
        assertThat(response.statusCode()).isEqualTo(200);
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8));

        List<String[]> events = readEvents(reader, e -> "response.failed".equals(e[0]));
        assertThat(events).extracting(e -> e[0]).contains("response.accepted", "response.delta", "response.failed");
        assertThat(events).extracting(e -> e[0]).doesNotContain("response.completed");
        assertThat(events.stream().filter(e -> "response.failed".equals(e[0])).count()).isEqualTo(1);
        JsonNode failed = JSON.readTree(events.get(events.size() - 1)[1]);
        assertThat(failed.path("code").asText()).isEqualTo("DEPENDENCY_UNAVAILABLE");
        assertThat(failed.path("message").asText()).doesNotContain("bogus");
    }

    @Test
    @DisplayName("流内读取超时 / 下游永不终态 → HTTP 200 + 恰一个 failed(DEPENDENCY_TIMEOUT)，限期内到达、下游断开、线程收敛")
    void downstreamReadTimeoutYieldsFailedTerminal() throws Exception {
        long baseline = gimbalAiReaderCount();
        STUB.holdOpenSilently(List.of(AiResponseStub.accepted(), AiResponseStub.delta("A")), 100);

        long start = System.nanoTime();
        HttpResponse<InputStream> response = postStreaming(gimbalToken(), "{\"text\":\"hi\"}");
        assertThat(response.statusCode()).isEqualTo(200);
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8));

        List<String[]> events = readEvents(reader, e -> "response.failed".equals(e[0]));
        long elapsed = (System.nanoTime() - start) / 1_000_000L;

        assertThat(events).extracting(e -> e[0]).doesNotContain("response.completed");
        assertThat(events.stream().filter(e -> "response.failed".equals(e[0])).count()).isEqualTo(1);
        assertThat(JSON.readTree(events.get(events.size() - 1)[1]).path("code").asText())
                .isEqualTo("DEPENDENCY_TIMEOUT");
        assertThat(elapsed).as("failed must arrive near read-timeout (1s)").isBetween(700L, 4000L);
        assertThat(STUB.awaitClientDisconnected(4000))
                .as("downstream exchange must be closed after in-stream timeout").isTrue();
        awaitReaderThreadsAtMost(baseline, 3000);
    }

    @Test
    @DisplayName("B1(c2) 外部客户端断开 → 下游交换被取消（stub 观测断开），reader 线程收敛")
    void externalClientDisconnectCancelsDownstream() throws Exception {
        long baseline = gimbalAiReaderCount();
        STUB.holdOpenSilently(List.of(AiResponseStub.accepted(), AiResponseStub.delta("A")), 100);

        HttpResponse<InputStream> response = postStreaming(gimbalToken(), "{\"text\":\"hi\"}");
        assertThat(response.statusCode()).isEqualTo(200);
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8));
        List<String[]> events = readEvents(reader, e -> "response.delta".equals(e[0]));
        assertThat(events).extracting(e -> e[0]).contains("response.delta");

        response.body().close(); // 外部客户端断开

        assertThat(STUB.awaitClientDisconnected(5000))
                .as("client disconnect must eventually cancel the downstream exchange").isTrue();
        awaitReaderThreadsAtMost(baseline, 3000);
    }

    private static long gimbalAiReaderCount() {
        return Thread.getAllStackTraces().keySet().stream()
                .filter(Thread::isAlive)
                .filter(thread -> "gimbal-ai-sse-reader".equals(thread.getName()))
                .count();
    }

    private static void awaitReaderThreadsAtMost(long baseline, long timeoutMillis) {
        long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
        while (System.nanoTime() < deadline && gimbalAiReaderCount() > baseline) {
            try {
                Thread.sleep(25);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                break;
            }
        }
        assertThat(gimbalAiReaderCount()).isLessThanOrEqualTo(baseline);
    }
}

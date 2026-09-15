package cn.yuanxin.mvp.web.gimbalai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * 云台 AI 文本透传下游客户端（JDK {@link HttpClient}；<b>SSE 流式</b>；无状态、无重试回退）。
 *
 * <p>固定契约（对 {@code POST {base}/internal/v1/ai/responses:stream}）：</p>
 * <ul>
 *   <li>Header：{@code X-Service-Name=medical-platform}、{@code X-API-Key}（配置）、
 *       {@code X-Request-Id}（每次调用服务端新生成）、{@code Idempotency-Key}
 *       （<b>每次调用全新</b>，故客户端重试会产生<b>新问题</b>；本增量无本地幂等存储）、
 *       {@code X-Protocol-Version=1.0}、{@code traceparent}（W3C）、
 *       {@code Accept: text/event-stream}、{@code Content-Type: application/json}；
 *       <b>不发送</b> Last-Event-ID（绝不续传）；</li>
 *   <li>Body：{@code {"protocol_version":"1.0","request_id":"<X-Request-Id>",
 *       "use_case":"APP_AGENT_CONVERSATION","input":{"text":"<用户文本>"}}}；不含
 *       {@code continuation_state}；</li>
 *   <li>预流：非 2xx → {@code UNAVAILABLE}；连接失败 → {@code UNAVAILABLE}；预流超时 → {@code TIMEOUT}；
 *       流内：由 {@link GimbalAiSseParser} 增量严格校验，读取超时 → {@code TIMEOUT}，传输/EOF 违规 →
 *       {@code MALFORMED}/{@code UNAVAILABLE}。</li>
 * </ul>
 *
 * <p><b>绝不</b>回退到一次性 {@code /internal/v1/ai/responses}；<b>绝不</b>合成答案。</p>
 *
 * <p><b>日志</b>：只记下游 requestId / HTTP 状态 / 下游错误码 / 失败分类；绝不记 API Key、
 * 用户文本、SSE 原文。</p>
 */
public class HttpGimbalAiClient implements GimbalAiClient {

    private static final Logger log = LoggerFactory.getLogger(HttpGimbalAiClient.class);

    static final String SERVICE_NAME = "medical-platform";
    static final String USE_CASE = "APP_AGENT_CONVERSATION";
    static final String PROTOCOL_VERSION = "1.0";
    static final String RESPONSES_STREAM_PATH = "/internal/v1/ai/responses:stream";

    private static final SecureRandom RANDOM = new SecureRandom();

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final URI endpoint;
    private final String apiKey;
    private final long readTimeoutMillis;

    public HttpGimbalAiClient(GimbalAiProperties properties, ObjectMapper objectMapper) {
        this(properties, objectMapper, HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(properties.connectTimeoutMillis()))
                .build());
    }

    /** 测试用构造器：注入自定义 HttpClient（如指向本地 stub 的连接池）。 */
    HttpGimbalAiClient(GimbalAiProperties properties, ObjectMapper objectMapper,
                       HttpClient httpClient) {
        this.objectMapper = objectMapper;
        this.httpClient = httpClient;
        this.endpoint = URI.create(properties.normalizedBaseUrl() + RESPONSES_STREAM_PATH);
        this.apiKey = properties.apiKey();
        this.readTimeoutMillis = properties.readTimeoutMillis();
    }

    @Override
    public GimbalAiStream openStream(String text) {
        String requestId = UUID.randomUUID().toString();
        String idempotencyKey = UUID.randomUUID().toString();
        String traceparent = newTraceparent();

        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .header("X-Service-Name", SERVICE_NAME)
                .header("X-API-Key", apiKey)
                .header("X-Request-Id", requestId)
                .header("Idempotency-Key", idempotencyKey)
                .header("X-Protocol-Version", PROTOCOL_VERSION)
                .header("traceparent", traceparent)
                .header("Accept", "text/event-stream")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        buildBody(requestId, text), StandardCharsets.UTF_8))
                .build();

        HttpResponse<InputStream> response = sendForHeaders(request, requestId);
        int status = response.statusCode();
        if (status < 200 || status >= 300) {
            String safeCode = safeProblemCode(readProblemBody(response.body()));
            log.warn("gimbal AI downstream non-2xx requestId={} status={} code={}",
                    requestId, status, safeCode == null ? "<none>" : safeCode);
            closeQuietly(response.body());
            throw new GimbalAiException(GimbalAiFailureKind.UNAVAILABLE,
                    "gimbal AI downstream returned a non-success status", status, safeCode);
        }
        GimbalAiSseParser parser = new GimbalAiSseParser(
                new TimeoutLineSource(response.body(), readTimeoutMillis));
        log.info("gimbal AI downstream stream opened requestId={} status={}", requestId, status);
        return new GimbalAiStream() {
            @Override
            public GimbalAiEvent next() {
                return parser.next();
            }

            @Override
            public void close() {
                parser.close();
            }
        };
    }

    /** 预流：以 read-timeout 约束"响应头到达"；预流超时 → TIMEOUT，连接失败 → UNAVAILABLE。 */
    private HttpResponse<InputStream> sendForHeaders(HttpRequest request, String requestId) {
        try {
            return httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream())
                    .get(readTimeoutMillis, TimeUnit.MILLISECONDS);
        } catch (TimeoutException timeout) {
            log.warn("gimbal AI downstream pre-stream timeout requestId={}", requestId);
            throw new GimbalAiException(GimbalAiFailureKind.TIMEOUT,
                    "gimbal AI downstream timed out before streaming");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new GimbalAiException(GimbalAiFailureKind.UNAVAILABLE,
                    "gimbal AI downstream call was interrupted");
        } catch (ExecutionException failure) {
            Throwable cause = failure.getCause();
            if (cause instanceof HttpTimeoutException) {
                throw new GimbalAiException(GimbalAiFailureKind.TIMEOUT,
                        "gimbal AI downstream timed out before streaming");
            }
            log.warn("gimbal AI downstream transport failure requestId={} exception={}",
                    requestId, cause == null ? "unknown" : cause.getClass().getSimpleName());
            throw new GimbalAiException(GimbalAiFailureKind.UNAVAILABLE,
                    "gimbal AI downstream transport failure");
        }
    }

    private String readProblemBody(InputStream body) {
        if (body == null) {
            return null;
        }
        try {
            return new String(body.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException unreadable) {
            return null;
        }
    }

    private static void closeQuietly(InputStream body) {
        if (body == null) {
            return;
        }
        try {
            body.close();
        } catch (IOException ignored) {
            // best effort
        }
    }

    private String buildBody(String requestId, String text) {
        try {
            ObjectNode root = objectMapper.createObjectNode();
            root.put("protocol_version", PROTOCOL_VERSION);
            root.put("request_id", requestId);
            root.put("use_case", USE_CASE);
            ObjectNode input = objectMapper.createObjectNode();
            input.put("text", text);
            root.set("input", input);
            return objectMapper.writeValueAsString(root);
        } catch (Exception encoding) {
            throw new GimbalAiException(GimbalAiFailureKind.UNAVAILABLE,
                    "gimbal AI downstream request could not be encoded");
        }
    }

    /** problem+json 的 code（仅用于日志；解析失败返回 null，绝不影响失败分类）。 */
    private String safeProblemCode(String body) {
        if (body == null || body.isBlank()) {
            return null;
        }
        try {
            JsonNode node = objectMapper.readTree(body).path("code");
            return node.isTextual() ? node.asText() : null;
        } catch (Exception ignored) {
            return null;
        }
    }

    private static String newTraceparent() {
        return "00-" + randomHex(16) + "-" + randomHex(8) + "-01";
    }

    private static String randomHex(int byteCount) {
        byte[] bytes = new byte[byteCount];
        RANDOM.nextBytes(bytes);
        StringBuilder builder = new StringBuilder(byteCount * 2);
        for (byte b : bytes) {
            builder.append(Character.forDigit((b >> 4) & 0xF, 16));
            builder.append(Character.forDigit(b & 0xF, 16));
        }
        return builder.toString();
    }

    /**
     * 带单次读取超时的 SSE 行源：工作线程阻塞读行入队；消费侧按 read-timeout 轮询。
     * 超时即关闭底层 InputStream（取消下游交换）并抛 {@code TIMEOUT}；传输失败抛
     * {@code UNAVAILABLE}。{@link #close()} 解除阻塞并取消连接（客户端断开时调用）。
     */
    private static final class TimeoutLineSource implements GimbalAiLineSource {

        private static final Object EOF = new Object();

        private final BufferedReader reader;
        private final long timeoutMillis;
        private final BlockingQueue<Object> queue = new LinkedBlockingQueue<>();
        private final Thread worker;

        TimeoutLineSource(InputStream body, long timeoutMillis) {
            this.reader = new BufferedReader(new InputStreamReader(body, StandardCharsets.UTF_8));
            this.timeoutMillis = timeoutMillis;
            this.worker = new Thread(this::pump, "gimbal-ai-sse-reader");
            this.worker.setDaemon(true);
            this.worker.start();
        }

        private void pump() {
            try {
                String line;
                while ((line = reader.readLine()) != null) {
                    queue.add(line);
                }
                queue.add(EOF);
            } catch (IOException io) {
                queue.add(io);
            }
        }

        @Override
        public String readLine() {
            Object item;
            try {
                item = queue.poll(timeoutMillis, TimeUnit.MILLISECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                close();
                throw new GimbalAiException(GimbalAiFailureKind.UNAVAILABLE,
                        "gimbal AI downstream read interrupted");
            }
            if (item == null) {
                close();
                throw new GimbalAiException(GimbalAiFailureKind.TIMEOUT,
                        "gimbal AI downstream stream read timed out");
            }
            if (item == EOF) {
                return null;
            }
            if (item instanceof IOException) {
                throw new GimbalAiException(GimbalAiFailureKind.UNAVAILABLE,
                        "gimbal AI downstream stream transport failure");
            }
            return (String) item;
        }

        @Override
        public void close() {
            try {
                reader.close();
            } catch (IOException ignored) {
                // best effort
            }
            worker.interrupt();
        }
    }
}

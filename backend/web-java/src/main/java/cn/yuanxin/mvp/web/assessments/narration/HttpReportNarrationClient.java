package cn.yuanxin.mvp.web.assessments.narration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 报告播报下游客户端（JDK {@link HttpClient}；<b>SSE 流式</b>；无状态、无重试回退）。
 *
 * <p>固定契约（对 {@code POST {base}/internal/v1/weijing/reports/assess:stream}）：</p>
 * <ul>
 *   <li>Header：{@code X-Service-Name=medical-platform}、{@code X-API-Key}（配置）、
 *       {@code X-Request-Id}（每次调用新生成）、{@code Idempotency-Key}（<b>每次调用全新</b>，
 *       故客户端重试会产生<b>新评估</b>；本增量无本地幂等存储）、{@code X-Protocol-Version=1.0}、
 *       {@code traceparent}（W3C）、{@code Accept: text/event-stream}（<b>不是</b>
 *       {@code application/json}）、{@code Content-Type: application/json}；
 *       <b>绝不转发</b>云台的 {@code Authorization}/{@code Cookie}/任何入站头，
 *       也<b>不发送</b> Last-Event-ID（绝不续传）；</li>
 *   <li>Body：<b>恰好</b> {@code {"pores":{...},"spots":{...},"surface_gloss":{...}}}，
 *       每组只含白名单四键 {@code score}/{@code severity}/{@code name}/{@code regions}；
 *       不加 {@code report_id}/{@code algorithm_version}/{@code protocol_version}/{@code use_case}/
 *       {@code input} 等任何额外键；{@code score}/{@code severity} 为 null 时原样序列化为 JSON null；</li>
 *   <li>预流：非 2xx → {@code UNAVAILABLE}；连接失败 → {@code UNAVAILABLE}；预流超时 → {@code TIMEOUT}；
 *       流内：由 {@link ReportNarrationSseParser} 增量严格校验，读取超时 → {@code TIMEOUT}，
 *       传输/EOF 违规 → {@code MALFORMED}/{@code UNAVAILABLE}。</li>
 * </ul>
 *
 * <p><b>有界性（防挂死/OOM）</b>：</p>
 * <ul>
 *   <li>预流以 {@code read-timeout} 约束"响应头到达"；超时/中断会 {@code cancel(true)} 该 future，
 *       并在迟到的响应上尽力关闭 body，避免交换滞留；</li>
 *   <li>非 2xx problem body 的读取上限 {@value #MAX_PROBLEM_BODY_BYTES} 字节、期限
 *       {@code min(read-timeout, }{@value #PROBLEM_BODY_TIMEOUT_MILLIS}{@code ms)}；超限/超时即放弃
 *       解析（code 记为 null），openStream 总能及时返回 JSON problem；</li>
 *   <li>流内行源：有界队列（容量 {@value TimeoutLineSource#QUEUE_CAPACITY}，{@code put} 反压）、
 *       单行硬上限 {@value TimeoutLineSource#MAX_LINE_BYTES} 字节（超出 → {@code MALFORMED}）、
 *       取消/超时先关<b>原始</b> InputStream（不取 BufferedReader 锁）再中断并 {@code join} 有界；
 *       终态文本长度上限见 {@link ReportNarrationSseParser#MAX_ACCUMULATED_CHARS}。</li>
 * </ul>
 *
 * <p><b>绝不</b>回退到一次性接口；<b>绝不</b>合成文案。</p>
 *
 * <p><b>日志</b>：只记下游 requestId / HTTP 状态 / 经 {@link ReportNarrationCodes} 归一的安全码 /
 * 失败分类；绝不记 API Key、评分值、区域值、{@code spoken_text}、SSE 原文。</p>
 *
 * <p>与 {@code gimbalai} 的 {@code HttpGimbalAiClient} 同源范式、刻意不共享。</p>
 */
public class HttpReportNarrationClient implements ReportNarrationClient {

    private static final Logger log = LoggerFactory.getLogger(HttpReportNarrationClient.class);

    static final String SERVICE_NAME = "medical-platform";
    static final String PROTOCOL_VERSION = "1.0";
    static final String REPORTS_STREAM_PATH = "/internal/v1/weijing/reports/assess:stream";

    /** 非 2xx problem body 的读取上限（字节）。 */
    static final int MAX_PROBLEM_BODY_BYTES = 8 * 1024;
    /** 非 2xx problem body 的读取期限上限（毫秒），与 read-timeout 取较小值。 */
    static final long PROBLEM_BODY_TIMEOUT_MILLIS = 2000;

    private static final SecureRandom RANDOM = new SecureRandom();

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final URI endpoint;
    private final String apiKey;
    private final long readTimeoutMillis;

    public HttpReportNarrationClient(ReportNarrationProperties properties, ObjectMapper objectMapper) {
        this(properties, objectMapper, HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(properties.connectTimeoutMillis()))
                .build());
    }

    /** 测试用构造器：注入自定义 HttpClient（如指向本地 stub 的连接池）。 */
    HttpReportNarrationClient(ReportNarrationProperties properties, ObjectMapper objectMapper,
                              HttpClient httpClient) {
        this.objectMapper = objectMapper;
        this.httpClient = httpClient;
        this.endpoint = URI.create(properties.normalizedBaseUrl() + REPORTS_STREAM_PATH);
        this.apiKey = properties.apiKey();
        this.readTimeoutMillis = properties.readTimeoutMillis();
    }

    @Override
    public ReportNarrationStream openStream(ReportNarrationScores scores) {
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
                        buildBody(scores), StandardCharsets.UTF_8))
                .build();

        HttpResponse<InputStream> response = sendForHeaders(request, requestId);
        int status = response.statusCode();
        if (status < 200 || status >= 300) {
            String safeCode = ReportNarrationCodes.sanitize(readProblemCode(response.body()));
            log.warn("report narration downstream non-2xx requestId={} status={} code={}",
                    requestId, status, safeCode == null ? "<none>" : safeCode);
            closeQuietly(response.body());
            throw new ReportNarrationException(ReportNarrationFailureKind.UNAVAILABLE,
                    "report narration downstream returned a non-success status", status, safeCode);
        }
        ReportNarrationSseParser parser = new ReportNarrationSseParser(
                new TimeoutLineSource(response.body(), readTimeoutMillis));
        log.info("report narration downstream stream opened requestId={} status={}", requestId, status);
        return new ReportNarrationStream() {
            @Override
            public ReportNarrationEvent next() {
                return parser.next();
            }

            @Override
            public void close() {
                parser.close();
            }
        };
    }

    /**
     * 预流：以 read-timeout 约束"响应头到达"。超时/中断时 {@code cancel(true)} 并尽力关闭迟到
     * 响应体（避免交换滞留）；预流超时 → TIMEOUT，连接失败 → UNAVAILABLE。
     */
    private HttpResponse<InputStream> sendForHeaders(HttpRequest request, String requestId) {
        CompletableFuture<HttpResponse<InputStream>> future =
                httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());
        try {
            return future.get(readTimeoutMillis, TimeUnit.MILLISECONDS);
        } catch (TimeoutException timeout) {
            cancelAndDrain(future);
            log.warn("report narration downstream pre-stream timeout requestId={}", requestId);
            throw new ReportNarrationException(ReportNarrationFailureKind.TIMEOUT,
                    "report narration downstream timed out before streaming");
        } catch (InterruptedException interrupted) {
            cancelAndDrain(future);
            Thread.currentThread().interrupt();
            throw new ReportNarrationException(ReportNarrationFailureKind.UNAVAILABLE,
                    "report narration downstream call was interrupted");
        } catch (ExecutionException failure) {
            Throwable cause = failure.getCause();
            if (cause instanceof HttpTimeoutException) {
                throw new ReportNarrationException(ReportNarrationFailureKind.TIMEOUT,
                        "report narration downstream timed out before streaming");
            }
            log.warn("report narration downstream transport failure requestId={} exception={}",
                    requestId, cause == null ? "unknown" : cause.getClass().getSimpleName());
            throw new ReportNarrationException(ReportNarrationFailureKind.UNAVAILABLE,
                    "report narration downstream transport failure");
        }
    }

    /** 取消预流 future，并在其"迟到完成"时尽力关闭响应体。 */
    private static void cancelAndDrain(CompletableFuture<?> future) {
        future.cancel(true);
        future.whenComplete((value, error) -> {
            if (value instanceof HttpResponse<?> response
                    && response.body() instanceof InputStream body) {
                closeQuietly(body);
            }
        });
    }

    /**
     * 有界读取非 2xx body 并返回其中的 {@code code} 文本（未归一）。
     *
     * <p>上限 {@value #MAX_PROBLEM_BODY_BYTES} 字节、期限 {@code min(read-timeout,
     * }{@value #PROBLEM_BODY_TIMEOUT_MILLIS}{@code ms)}；超限只解析已读到的前缀，超时/异常返回
     * {@code null}。无论结果如何都关闭 body，保证 openStream 及时返回。</p>
     */
    private String readProblemCode(InputStream body) {
        if (body == null) {
            return null;
        }
        long deadlineMillis = Math.min(readTimeoutMillis, PROBLEM_BODY_TIMEOUT_MILLIS);
        ExecutorService executor = Executors.newSingleThreadExecutor(runnable -> {
            Thread thread = new Thread(runnable, "report-narration-problem-body");
            thread.setDaemon(true);
            return thread;
        });
        try {
            Future<String> future = executor.submit(
                    () -> new String(body.readNBytes(MAX_PROBLEM_BODY_BYTES), StandardCharsets.UTF_8));
            String json = future.get(deadlineMillis, TimeUnit.MILLISECONDS);
            try {
                JsonNode node = objectMapper.readTree(json).path("code");
                return node.isTextual() ? node.asText() : null;
            } catch (Exception unparseable) {
                return null;
            }
        } catch (Exception bounded) {
            return null;
        } finally {
            closeQuietly(body); // 解除工作线程的阻塞读
            executor.shutdownNow();
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

    /**
     * 组装 AI body：顶层<b>恰好</b>三个键（pores、spots、surface_gloss，顺序固定），
     * 每组恰好白名单四键，使用 {@code objectMapper}（不手拼字符串）。
     */
    private String buildBody(ReportNarrationScores scores) {
        try {
            ObjectNode root = objectMapper.createObjectNode();
            root.set("pores", groupNode(scores.pores()));
            root.set("spots", groupNode(scores.spots()));
            root.set("surface_gloss", groupNode(scores.surfaceGloss()));
            return objectMapper.writeValueAsString(root);
        } catch (Exception encoding) {
            throw new ReportNarrationException(ReportNarrationFailureKind.UNAVAILABLE,
                    "report narration downstream request could not be encoded");
        }
    }

    private ObjectNode groupNode(ReportNarrationScores.ScoreGroup group) {
        ObjectNode node = objectMapper.createObjectNode();
        putScore(node, "score", group.score());
        putSeverity(node, "severity", group.severity());
        node.put("name", group.name());
        ArrayNode regions = objectMapper.createArrayNode();
        for (ReportNarrationScores.Region region : group.regions()) {
            ObjectNode regionNode = objectMapper.createObjectNode();
            regionNode.put("region", region.region());
            regionNode.put("name", region.name());
            putScore(regionNode, "score", region.score());
            putSeverity(regionNode, "severity", region.severity());
            regions.add(regionNode);
        }
        node.set("regions", regions);
        return node;
    }

    /** score 为 null 时原样写 JSON null（绝不 coerce 成 0）。 */
    private static void putScore(ObjectNode node, String field, BigDecimal score) {
        if (score == null) {
            node.putNull(field);
        } else {
            node.put(field, score);
        }
    }

    /** severity 为 null 时原样写 JSON null。 */
    private static void putSeverity(ObjectNode node, String field, String severity) {
        if (severity == null) {
            node.putNull(field);
        } else {
            node.put(field, severity);
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
     * 带单次读取超时的 SSE 行源（有界、可取消）。
     *
     * <p>工作线程从<b>原始</b> {@code InputStream} 逐字节读取（经 {@link BufferedInputStream}
     * 吞吐优化），单行硬上限 {@value #MAX_LINE_BYTES} 字节（超出 → {@code MALFORMED}），
     * 以容量 {@value #QUEUE_CAPACITY} 的有界队列 + 可中断 {@code put} 形成反压。</p>
     *
     * <p><b>取消/超时</b>：先关闭<b>原始</b>流（其 {@code close()} 不取 {@code BufferedReader}
     * 的锁，可直接解除工作线程的 socket 阻塞读），再 {@code interrupt()} 并 {@code join}
     * （上限 {@value #CLOSE_JOIN_MILLIS} ms），绝不以 {@code BufferedReader.close()} 作为解阻塞手段。
     * 与 {@code gimbalai} 的 {@code TimeoutLineSource} 同源范式、刻意不共享。</p>
     */
    private static final class TimeoutLineSource implements ReportNarrationLineSource {

        private static final Object EOF = new Object();
        /** 有界队列容量（反压）。 */
        static final int QUEUE_CAPACITY = 1024;
        /** 单行原始字节硬上限。 */
        static final int MAX_LINE_BYTES = 64 * 1024;
        /** close() 等待工作线程退出的上限。 */
        static final long CLOSE_JOIN_MILLIS = 500;

        private final InputStream raw;
        private final BufferedInputStream buffered;
        private final java.io.PushbackInputStream input;
        private final long timeoutMillis;
        private final BlockingQueue<Object> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
        private final AtomicBoolean closed = new AtomicBoolean();
        private final Thread worker;

        TimeoutLineSource(InputStream raw, long timeoutMillis) {
            this.raw = raw;
            this.buffered = new BufferedInputStream(raw, 8192);
            this.input = new java.io.PushbackInputStream(buffered, 1);
            this.timeoutMillis = timeoutMillis;
            this.worker = new Thread(this::pump, "report-narration-sse-reader");
            this.worker.setDaemon(true);
            this.worker.start();
        }

        private void pump() {
            try {
                String line;
                while ((line = readBoundedLine()) != null) {
                    if (closed.get()) {
                        return;
                    }
                    enqueue(line);
                }
                if (!closed.get()) {
                    enqueue(EOF);
                }
            } catch (LineTooLongException tooLong) {
                if (!closed.get()) {
                    enqueue(new ReportNarrationException(ReportNarrationFailureKind.MALFORMED,
                            "report narration downstream SSE line exceeded the maximum length"));
                }
            } catch (IOException io) {
                if (!closed.get()) {
                    enqueue(io);
                }
            }
        }

        /** 逐字节读到行终止符（\n / \r\n / \r）或 EOF；超 {@value #MAX_LINE_BYTES} 抛异常。 */
        private String readBoundedLine() throws IOException {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            int b;
            while ((b = input.read()) != -1) {
                if (b == '\n') {
                    return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
                }
                if (b == '\r') {
                    int next = input.read();
                    if (next != -1 && next != '\n') {
                        input.unread(next);
                    }
                    return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
                }
                if (buffer.size() >= MAX_LINE_BYTES) {
                    throw new LineTooLongException();
                }
                buffer.write(b);
            }
            if (buffer.size() == 0) {
                return null;
            }
            return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
        }

        private void enqueue(Object item) {
            try {
                queue.put(item); // 满时阻塞形成反压
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
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
                throw new ReportNarrationException(ReportNarrationFailureKind.UNAVAILABLE,
                        "report narration downstream read interrupted");
            }
            if (item == null) {
                close();
                throw new ReportNarrationException(ReportNarrationFailureKind.TIMEOUT,
                        "report narration downstream stream read timed out");
            }
            if (item == EOF) {
                return null;
            }
            if (item instanceof ReportNarrationException failure) {
                throw failure;
            }
            if (item instanceof IOException) {
                throw new ReportNarrationException(ReportNarrationFailureKind.UNAVAILABLE,
                        "report narration downstream stream transport failure");
            }
            return (String) item;
        }

        @Override
        public void close() {
            if (!closed.compareAndSet(false, true)) {
                return;
            }
            // 先关原始流：其 close() 不取 BufferedReader 锁，直接解除工作线程的阻塞读。
            closeQuietly(raw);
            worker.interrupt();
            try {
                worker.join(CLOSE_JOIN_MILLIS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    /** 单行超出硬上限的内部信号（不对外）。 */
    private static final class LineTooLongException extends IOException {
        LineTooLongException() {
            super("line too long");
        }
    }
}

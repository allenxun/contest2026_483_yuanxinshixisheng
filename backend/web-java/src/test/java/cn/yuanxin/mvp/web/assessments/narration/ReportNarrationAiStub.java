package cn.yuanxin.mvp.web.assessments.narration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 报告评估 AI 服务 {@code POST /internal/v1/weijing/reports/assess:stream} 的本地 HTTP stub
 * （随机端口）。记录方法/路径/首值 header/原始 body；支持脚本化分帧 SSE、静默保持、
 * 慢/巨 problem body、静默打点（检测客户端断开）。
 *
 * <p>本 stub 与 {@code gimbalai/AiResponseStub} 同源思路但<b>各自独立</b>，未修改对方；
 * 事件名与 completed 字段（{@code spoken_text}）按报告评估契约。测试用，不访问真实服务；
 * 使用的 key 一律是明显假值。</p>
 */
public final class ReportNarrationAiStub implements AutoCloseable {

    public static final String FAKE_API_KEY = "FAKE-NARRATION-KEY-DO-NOT-USE";

    private static final ObjectMapper JSON = new ObjectMapper();

    public record Captured(String method, String path, Map<String, String> headers, String body) {
        public String header(String name) {
            return headers.get(name.toLowerCase(Locale.ROOT));
        }
    }

    public static String accepted() {
        return frame("response.accepted", "{\"request_id\":\"stub-accepted\"}");
    }

    public static String delta(String text) {
        return frame("response.delta", "{\"delta\":" + quote(text) + "}");
    }

    public static String completed(String spokenText) {
        return frame("response.completed", "{\"spoken_text\":" + quote(spokenText) + "}");
    }

    public static String failed(String code) {
        return frame("response.failed", "{\"code\":" + quote(code) + "}");
    }

    /** 便捷合法流：accepted + 两个 delta + completed。 */
    public static String sse(String spokenText) {
        String first = spokenText.length() > 1 ? spokenText.substring(0, 1) : spokenText;
        String second = spokenText.length() > 1 ? spokenText.substring(1) : "";
        return accepted() + delta(first) + delta(second) + completed(spokenText);
    }

    private static String frame(String event, String json) {
        return "event: " + event + "\ndata: " + json + "\n\n";
    }

    private static String quote(String value) {
        try {
            return JSON.writeValueAsString(value);
        } catch (Exception impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private final List<Captured> requests = new CopyOnWriteArrayList<>();
    private final AtomicBoolean clientDisconnected = new AtomicBoolean();

    private volatile int status = 200;
    private volatile String body = sse("stub narration");
    private volatile List<String> scriptFrames = null;
    private volatile long holdBeforeFirstFrameMillis = 0;
    private volatile long holdBeforeHeadersMillis = 0;
    private volatile long holdOpenSilentlyMillis = 0;
    private volatile String slowProblemPrefix = null;
    private volatile long slowProblemHoldMillis = 0;

    private HttpServer server;

    public void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", this::handle);
        server.start();
    }

    public String baseUrl() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    /** 固定状态/整段 body（用于错误与非流场景）。 */
    public void respond(int responseStatus, String responseBody) {
        clearModes();
        this.status = responseStatus;
        this.body = responseBody;
    }

    /** 分帧流：逐帧 flush。 */
    public void script(List<String> frames) {
        clearModes();
        this.scriptFrames = List.copyOf(frames);
        this.status = 200;
    }

    /** 连响应头都保持静默（触发客户端预流超时；随后写 body 以观测客户端是否已断开）。 */
    public void holdHeadersSilently(long millis) {
        clearModes();
        this.holdBeforeHeadersMillis = millis;
        this.status = 200;
    }

    /** 发响应头后、首帧前保持连接静默（触发客户端读取超时）。 */
    public void holdConnectionSilently(long millis) {
        clearModes();
        this.holdBeforeFirstFrameMillis = millis;
        this.scriptFrames = List.of();
        this.status = 200;
    }

    /**
     * 发完 frames 后"永不发送终态"：每 {@code probeMillis} 静默写入一个单字节 {@code ':'} 并 flush；
     * 一旦客户端断开，写入抛 IOException，stub 记录 {@link #clientDisconnected}。
     */
    public void holdOpenSilently(List<String> preFrames, long probeMillis) {
        clearModes();
        this.scriptFrames = List.copyOf(preFrames);
        this.holdOpenSilentlyMillis = Math.max(1, probeMillis);
        this.status = 200;
    }

    /** 非 2xx 慢 problem body：chunked 发送 prefix 后保持 holdMillis（触发读取期限）。 */
    public void slowProblemBody(int responseStatus, String prefix, long holdMillis) {
        clearModes();
        this.status = responseStatus;
        this.slowProblemPrefix = prefix;
        this.slowProblemHoldMillis = holdMillis;
    }

    public boolean clientDisconnected() {
        return clientDisconnected.get();
    }

    public boolean awaitClientDisconnected(long timeoutMillis) {
        long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
        while (System.nanoTime() < deadline) {
            if (clientDisconnected.get()) {
                return true;
            }
            sleep(25);
        }
        return clientDisconnected.get();
    }

    public List<Captured> requests() {
        return requests;
    }

    public Captured lastRequest() {
        return requests.isEmpty() ? null : requests.get(requests.size() - 1);
    }

    public void reset() {
        clearModes();
        this.status = 200;
        this.body = sse("stub narration");
        this.requests.clear();
        this.clientDisconnected.set(false);
    }

    private void clearModes() {
        this.scriptFrames = null;
        this.holdBeforeFirstFrameMillis = 0;
        this.holdBeforeHeadersMillis = 0;
        this.holdOpenSilentlyMillis = 0;
        this.slowProblemPrefix = null;
        this.slowProblemHoldMillis = 0;
    }

    private void handle(HttpExchange exchange) throws IOException {
        byte[] raw = exchange.getRequestBody().readAllBytes();
        Map<String, String> headers = new LinkedHashMap<>();
        exchange.getRequestHeaders().forEach((name, values) ->
                headers.put(name.toLowerCase(Locale.ROOT), values.isEmpty() ? null : values.get(0)));
        requests.add(new Captured(exchange.getRequestMethod(),
                exchange.getRequestURI().getPath(), headers,
                new String(raw, StandardCharsets.UTF_8)));

        boolean stream = exchange.getRequestURI().getPath().endsWith(":stream");
        try {
            if (stream && status >= 200 && status < 300) {
                streamResponse(exchange);
            } else {
                fixedResponse(exchange, stream);
            }
        } catch (IOException clientGone) {
            clientDisconnected.set(true);
        } finally {
            exchange.close();
        }
    }

    private void streamResponse(HttpExchange exchange) throws IOException {
        if (holdBeforeHeadersMillis > 0) {
            sleep(holdBeforeHeadersMillis);
        }
        exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
        exchange.sendResponseHeaders(status, 0); // chunked
        OutputStream out = exchange.getResponseBody();
        if (holdBeforeFirstFrameMillis > 0) {
            sleep(holdBeforeFirstFrameMillis);
        }
        List<String> frames = scriptFrames;
        if (frames == null) {
            out.write(body.getBytes(StandardCharsets.UTF_8));
            out.flush();
            return;
        }
        for (String frame : frames) {
            out.write(frame.getBytes(StandardCharsets.UTF_8));
            out.flush();
        }
        long probeMillis = holdOpenSilentlyMillis;
        if (probeMillis > 0) {
            long maxProbes = Math.max(1, 10_000 / probeMillis); // ~10s 上限，防测试挂死
            for (long i = 0; i < maxProbes; i++) {
                sleep(probeMillis);
                out.write(':');
                out.flush();
            }
        }
    }

    private void fixedResponse(HttpExchange exchange, boolean stream) throws IOException {
        exchange.getResponseHeaders().set("Content-Type",
                stream ? "text/event-stream" : "application/json");
        String prefix = slowProblemPrefix;
        if (prefix != null && slowProblemHoldMillis > 0) {
            exchange.sendResponseHeaders(status, 0); // chunked trickle
            OutputStream out = exchange.getResponseBody();
            out.write(prefix.getBytes(StandardCharsets.UTF_8));
            out.flush();
            sleep(slowProblemHoldMillis);
            out.write("}".getBytes(StandardCharsets.UTF_8));
            out.flush();
            return;
        }
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public void close() {
        if (server != null) {
            server.stop(0);
        }
    }
}

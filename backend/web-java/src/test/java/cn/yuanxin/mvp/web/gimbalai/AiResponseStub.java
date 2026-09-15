package cn.yuanxin.mvp.web.gimbalai;

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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * AI 服务 {@code POST /internal/v1/ai/responses:stream} 的本地 HTTP stub（随机端口）。
 * 记录方法/路径/首值 header/原始 body；支持脚本化分帧 SSE（逐帧 flush）与"held completed"
 * 门闩，供流式/时序断言。测试用，不访问真实服务。
 */
final class AiResponseStub implements AutoCloseable {

    record Captured(String method, String path, Map<String, String> headers, String body) {
        String header(String name) {
            return headers.get(name.toLowerCase(Locale.ROOT));
        }
    }

    private static final String DEFAULT_BODY = sse("stub answer");

    /** 便捷构造：accepted + 两个 delta + completed 的合法 SSE 流。 */
    static String sse(String answerText) {
        return "event: response.accepted\ndata: {\"request_id\":\"stub-accepted\"}\n\n"
                + "event: response.delta\ndata: {\"delta\":\"stub \"}\n\n"
                + "event: response.delta\ndata: {\"delta\":\"answer\"}\n\n"
                + "event: response.completed\ndata: {\"answer\":{\"text\":\"" + answerText
                + "\"},\"usage\":{\"tokens\":1}}\n\n";
    }

    static String accepted() {
        return "event: response.accepted\ndata: {\"request_id\":\"stub-accepted\"}\n\n";
    }

    static String delta(String text) {
        return "event: response.delta\ndata: {\"delta\":\"" + text + "\"}\n\n";
    }

    static String completed(String answerText) {
        return "event: response.completed\ndata: {\"answer\":{\"text\":\"" + answerText + "\"}}\n\n";
    }

    private final List<Captured> requests = new CopyOnWriteArrayList<>();
    private volatile int status = 200;
    private volatile String body = DEFAULT_BODY;
    private volatile long delayMillis = 0;

    private volatile List<String> scriptFrames = null;
    private volatile long interFrameDelayMillis = 0;
    private volatile long holdBeforeFirstFrameMillis = 0;
    private volatile long holdAfterFramesMillis = 0;
    private volatile long holdBeforeHeadersMillis = 0;
    private volatile String heldFrame = null;
    private volatile CountDownLatch heldGate = null;

    private HttpServer server;

    void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", this::handle);
        server.start();
    }

    String baseUrl() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    /** 固定状态/整段 body（用于错误与非流场景）。 */
    void respond(int responseStatus, String responseBody) {
        this.status = responseStatus;
        this.body = responseBody;
        this.scriptFrames = null;
        this.heldFrame = null;
        this.heldGate = null;
    }

    /** 分帧流：逐帧 flush，帧间可延迟。 */
    void script(List<String> frames, long interFrameDelayMillis) {
        this.scriptFrames = frames;
        this.interFrameDelayMillis = interFrameDelayMillis;
        this.heldFrame = null;
        this.heldGate = null;
        this.holdBeforeFirstFrameMillis = 0;
        this.status = 200;
    }

    /** 分帧流：先发 preFrames，再等待门闩，最后发 heldFrame（用于"delta 先于 completed 可观测"）。 */
    void scriptHeld(List<String> preFrames, String heldFrame) {
        this.scriptFrames = preFrames;
        this.heldFrame = heldFrame;
        this.heldGate = new CountDownLatch(1);
        this.interFrameDelayMillis = 0;
        this.holdBeforeFirstFrameMillis = 0;
        this.status = 200;
    }

    /** 发响应头后、首帧前保持连接静默，用于触发客户端读取超时。 */
    void holdConnectionSilently(long millis) {
        this.holdBeforeFirstFrameMillis = millis;
        this.scriptFrames = List.of();
        this.heldFrame = null;
        this.heldGate = null;
        this.status = 200;
    }

    /** 连响应头都保持静默，用于触发客户端预流（到首响应头）超时。 */
    void holdHeadersSilently(long millis) {
        this.holdBeforeHeadersMillis = millis;
        this.scriptFrames = List.of();
        this.heldFrame = null;
        this.heldGate = null;
        this.status = 200;
    }

    /** 先发 frames，再保持连接静默 holdMillis（用于触发流内读取超时）。 */
    void scriptThenHold(List<String> frames, long holdMillis) {
        this.scriptFrames = frames;
        this.holdAfterFramesMillis = holdMillis;
        this.heldFrame = null;
        this.heldGate = null;
        this.status = 200;
    }

    boolean heldPending() {
        CountDownLatch gate = heldGate;
        return gate != null && gate.getCount() > 0;
    }

    void releaseHeld() {
        CountDownLatch gate = heldGate;
        if (gate != null) {
            gate.countDown();
        }
    }

    void delay(long millis) {
        this.delayMillis = millis;
    }

    List<Captured> requests() {
        return requests;
    }

    Captured lastRequest() {
        return requests.isEmpty() ? null : requests.get(requests.size() - 1);
    }

    void reset() {
        this.status = 200;
        this.body = DEFAULT_BODY;
        this.delayMillis = 0;
        this.scriptFrames = null;
        this.interFrameDelayMillis = 0;
        this.holdBeforeFirstFrameMillis = 0;
        this.holdAfterFramesMillis = 0;
        this.holdBeforeHeadersMillis = 0;
        this.heldFrame = null;
        this.heldGate = null;
        this.requests.clear();
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
        if (stream && status >= 200 && status < 300) {
            streamResponse(exchange);
        } else {
            fixedResponse(exchange);
        }
        exchange.close();
    }

    private void streamResponse(HttpExchange exchange) throws IOException {
        if (holdBeforeHeadersMillis > 0) {
            sleep(holdBeforeHeadersMillis);
        }
        exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
        exchange.sendResponseHeaders(status, 0); // chunked
        OutputStream out = exchange.getResponseBody();
        try {
            if (holdBeforeFirstFrameMillis > 0) {
                sleep(holdBeforeFirstFrameMillis);
            }
            List<String> frames = scriptFrames;
            if (frames != null) {
                for (String frame : frames) {
                    out.write(frame.getBytes(StandardCharsets.UTF_8));
                    out.flush();
                    if (interFrameDelayMillis > 0) {
                        sleep(interFrameDelayMillis);
                    }
                }
                if (heldFrame != null) {
                    CountDownLatch gate = heldGate;
                    if (gate != null) {
                        try {
                            gate.await(10, TimeUnit.SECONDS);
                        } catch (InterruptedException interrupted) {
                            Thread.currentThread().interrupt();
                        }
                    }
                    out.write(heldFrame.getBytes(StandardCharsets.UTF_8));
                    out.flush();
                }
                if (holdAfterFramesMillis > 0) {
                    sleep(holdAfterFramesMillis);
                }
            } else {
                out.write(body.getBytes(StandardCharsets.UTF_8));
                out.flush();
            }
        } catch (IOException clientGone) {
            // 客户端断开：忽略。
        } finally {
            try {
                out.close();
            } catch (IOException ignored) {
                // ignore
            }
        }
    }

    private void fixedResponse(HttpExchange exchange) throws IOException {
        if (delayMillis > 0) {
            sleep(delayMillis);
        }
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type",
                exchange.getRequestURI().getPath().endsWith(":stream")
                        ? "text/event-stream" : "application/json");
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

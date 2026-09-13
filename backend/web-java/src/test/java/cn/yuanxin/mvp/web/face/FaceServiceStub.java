package cn.yuanxin.mvp.web.face;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * InsightFace 服务的本地 HTTP stub（随机端口；测试用，不发真实人脸、不访问真实服务）。
 * 记录方法/路径/内部 token 头/原始 body，供 wire 与脱敏断言。
 */
final class FaceServiceStub implements AutoCloseable {

    record Request(String method, String path, String internalToken, byte[] body) {
    }

    private final List<Request> requests = new CopyOnWriteArrayList<>();
    private volatile int healthStatus = 200;
    private volatile String healthBody =
            "{\"status\":\"ok\",\"model_loaded\":true,\"model_version\":\"buffalo_l@fake\","
                    + "\"liveness\":{\"supported\":false,\"reason\":\"no liveness model\"}}";
    private volatile int extractStatus = 200;
    private volatile String extractBody = "{\"face_count\":1,\"request_id\":\"req-extract\"}";
    private volatile int verifyStatus = 200;
    private volatile String verifyBody =
            "{\"matched\":true,\"similarity\":0.9,\"threshold\":0.4,\"request_id\":\"req-verify\"}";
    private volatile long delayMillis = 0;

    private HttpServer server;

    void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", this::handle);
        server.start();
    }

    String baseUrl() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    void health(int status, String body) {
        this.healthStatus = status;
        this.healthBody = body;
    }

    void extract(int status, String body) {
        this.extractStatus = status;
        this.extractBody = body;
    }

    void verify(int status, String body) {
        this.verifyStatus = status;
        this.verifyBody = body;
    }

    void delay(long millis) {
        this.delayMillis = millis;
    }

    List<Request> requests() {
        return requests;
    }

    Request last(String method, String pathSuffix) {
        for (int i = requests.size() - 1; i >= 0; i--) {
            Request r = requests.get(i);
            if (r.method().equalsIgnoreCase(method) && r.path().endsWith(pathSuffix)) {
                return r;
            }
        }
        return null;
    }

    private void handle(HttpExchange exchange) throws IOException {
        byte[] body = exchange.getRequestBody().readAllBytes();
        requests.add(new Request(exchange.getRequestMethod(), exchange.getRequestURI().getPath(),
                exchange.getRequestHeaders().getFirst("X-Internal-Token"), body));
        if (delayMillis > 0) {
            try {
                Thread.sleep(delayMillis);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }
        String path = exchange.getRequestURI().getPath();
        int status;
        String response;
        if (path.endsWith("/v1/health")) {
            status = healthStatus;
            response = healthBody;
        } else if (path.endsWith("/v1/extract")) {
            status = extractStatus;
            response = extractBody;
        } else if (path.endsWith("/v1/verify")) {
            status = verifyStatus;
            response = verifyBody;
        } else {
            status = 404;
            response = "{\"error\":{\"code\":\"NOT_FOUND\",\"message\":\"unknown\",\"retryable\":false}}";
        }
        byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }

    @Override
    public void close() {
        if (server != null) {
            server.stop(0);
        }
    }

    static String errorBody(String code, boolean retryable, String requestId) {
        return "{\"error\":{\"code\":\"" + code + "\",\"message\":\"stub " + code
                + "\",\"retryable\":" + retryable + ",\"request_id\":\"" + requestId + "\"}}";
    }
}

package cn.yuanxin.mvp.web.face;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
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
 *
 * <p>为让 1:1 映射测试专注在 {@code InsightFaceCareVerifier} 的映射逻辑上，
 * {@link #verify(int, String)} 会对缺失 {@code liveness} 的成功体补一个
 * {@code {"supported":true,"passed":true,...}}（模拟"支持活体且本次样本通过"的服务）；
 * 需要逐字检验畸形/活体缺失响应的测试请用 {@link #verifyRaw(int, String)}（不做任何补全）。</p>
 *
 * <p>新端点（search/quality/register/get/delete）各自有可设置的响应体，默认返回合规的成功形状。</p>
 */
final class FaceServiceStub implements AutoCloseable {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    record Request(String method, String path, String internalToken, byte[] body) {
    }

    private final List<Request> requests = new CopyOnWriteArrayList<>();
    private volatile int healthStatus = 200;
    private volatile String healthBody =
            "{\"status\":\"ok\",\"model_loaded\":true,\"model_version\":\"buffalo_l@fake\","
                    + "\"library_revision\":3,"
                    + "\"liveness\":{\"supported\":false,\"reason\":\"no liveness model\"}}";
    private volatile int extractStatus = 200;
    private volatile String extractBody = "{\"face_count\":1,\"request_id\":\"req-extract\"}";
    private volatile int qualityStatus = 200;
    private volatile String qualityBody =
            "{\"face_count\":1,\"faces\":[{\"quality\":{\"min_acceptable\":true,"
                    + "\"liveness\":{\"supported\":false}},\"largest_face\":true}],"
                    + "\"largest_face_index\":0,\"liveness\":{\"supported\":false},"
                    + "\"library_revision\":3,\"request_id\":\"req-quality\"}";
    private volatile int searchStatus = 200;
    private volatile String searchBody =
            "{\"decision\":\"no_match\",\"ambiguous\":false,\"subject_count\":0,\"top_k\":5,"
                    + "\"reasons\":[],\"policy_version\":\"search-v1\","
                    + "\"model_version\":\"buffalo_l@fake\",\"library_revision\":3,"
                    + "\"request_id\":\"req-search\"}";
    private volatile int verifyStatus = 200;
    private volatile String verifyBody =
            "{\"matched\":true,\"similarity\":0.9,\"threshold\":0.4,\"request_id\":\"req-verify\"}";
    private volatile int registerStatus = 200;
    private volatile String registerBody =
            "{\"subject_id\":\"subj-1\",\"namespace\":\"openvela-mvp\",\"created\":true,"
                    + "\"created_at\":\"2026-01-01T00:00:00+00:00\","
                    + "\"updated_at\":\"2026-01-01T00:00:00+00:00\",\"embedding_dim\":512,"
                    + "\"model_version\":\"buffalo_l@fake\",\"quality\":{},\"library_revision\":4,"
                    + "\"request_id\":\"req-register\"}";
    private volatile int getStatus = 200;
    private volatile String getBody =
            "{\"subject_id\":\"subj-1\",\"namespace\":\"openvela-mvp\",\"embedding_dim\":512,"
                    + "\"model_version\":\"buffalo_l@fake\",\"created_at\":\"2026-01-01T00:00:00+00:00\","
                    + "\"updated_at\":\"2026-01-01T00:00:00+00:00\",\"library_revision\":4,"
                    + "\"request_id\":\"req-get\"}";
    private volatile int deleteStatus = 200;
    private volatile String deleteBody =
            "{\"deleted\":true,\"subject_id\":\"subj-1\",\"namespace\":\"openvela-mvp\","
                    + "\"library_revision\":5,\"request_id\":\"req-delete\"}";
    private volatile long delayMillis = 0;
    private volatile boolean rawVerify = false;

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

    void quality(int status, String body) {
        this.qualityStatus = status;
        this.qualityBody = body;
    }

    void search(int status, String body) {
        this.searchStatus = status;
        this.searchBody = body;
    }

    void verify(int status, String body) {
        this.rawVerify = false;
        this.verifyStatus = status;
        this.verifyBody = body;
    }

    /** 逐字返回 body（不补 {@code liveness}），用于严格契约判别测试。 */
    void verifyRaw(int status, String body) {
        this.rawVerify = true;
        this.verifyStatus = status;
        this.verifyBody = body;
    }

    void register(int status, String body) {
        this.registerStatus = status;
        this.registerBody = body;
    }

    void get(int status, String body) {
        this.getStatus = status;
        this.getBody = body;
    }

    void delete(int status, String body) {
        this.deleteStatus = status;
        this.deleteBody = body;
    }

    void delay(long millis) {
        this.delayMillis = millis;
    }

    List<Request> requests() {
        return requests;
    }

    int count(String method, String pathSuffix) {
        int n = 0;
        for (Request r : requests) {
            if (r.method().equalsIgnoreCase(method) && r.path().endsWith(pathSuffix)) {
                n++;
            }
        }
        return n;
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
        String method = exchange.getRequestMethod();
        String path = exchange.getRequestURI().getPath();
        requests.add(new Request(method, path,
                exchange.getRequestHeaders().getFirst("X-Internal-Token"), body));
        if (delayMillis > 0) {
            try {
                Thread.sleep(delayMillis);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }
        int status;
        String response;
        if (path.endsWith("/v1/health")) {
            status = healthStatus;
            response = healthBody;
        } else if (path.endsWith("/v1/extract")) {
            status = extractStatus;
            response = extractBody;
        } else if (path.endsWith("/v1/quality")) {
            status = qualityStatus;
            response = qualityBody;
        } else if (path.endsWith("/search")) {
            status = searchStatus;
            response = searchBody;
        } else if (path.endsWith("/v1/verify")) {
            status = verifyStatus;
            response = maybeAugmentVerify(status, verifyBody);
        } else if (path.endsWith("/subjects") && method.equalsIgnoreCase("POST")) {
            status = registerStatus;
            response = registerBody;
        } else if (path.matches(".*/subjects/[^/]+$") && method.equalsIgnoreCase("GET")) {
            status = getStatus;
            response = getBody;
        } else if (path.matches(".*/subjects/[^/]+$") && method.equalsIgnoreCase("DELETE")) {
            status = deleteStatus;
            response = deleteBody;
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

    /**
     * 2xx 成功体若缺 {@code liveness} 段，补一个 {@code supported=true} 的块——模拟一个
     * (1) 支持活体、且 (2) 已通过 {@code require_liveness=true} 门 的服务；缺/为 false 会被
     * Java 客户端按活体 fail-closed 拒绝（见 {@code FaceServiceClientStrictVerifyTest}）。
     */
    private String maybeAugmentVerify(int status, String body) {
        if (rawVerify || status < 200 || status >= 300) {
            return body;
        }
        try {
            JsonNode root = MAPPER.readTree(body);
            if (root == null || !root.isObject() || root.has("liveness")) {
                return body;
            }
            ((ObjectNode) root).set("liveness",
                    MAPPER.createObjectNode().put("supported", true).put("passed", true)
                            .put("reason", "stub-capable"));
            return MAPPER.writeValueAsString(root);
        } catch (Exception notJson) {
            return body;
        }
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
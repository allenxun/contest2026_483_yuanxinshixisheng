package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.aliyun.oss.OSS;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link OssStorageAdapter} 的 <b>本地 HTTP stub</b> 测试（不访问真实 OSS）：用
 * {@code com.sun.net.httpserver.HttpServer} 绑定本机随机端口，验证 wire 行为与失败分类。
 * 使用明显假凭据与假 bucket。若 SDK 选址使 stub 不可行，则相应断言应如实失败/跳过——
 * 不使用推测。
 */
class OssStorageAdapterTest {

    private static final String BUCKET = "fake-bucket-do-not-use";
    private static final String ENDPOINT = "https://oss-cn-hangzhou.aliyuncs.com";
    private static final byte[] IMAGE = "fake-image-bytes-0123456789".getBytes(StandardCharsets.UTF_8);
    private static final String KEY = "dev/assessment_source/00000000-0000-0000-0000-000000000001";

    private OssHttpStub stub;
    private OSS oss;
    private OssStorageAdapter adapter;

    @BeforeEach
    void setUp() throws IOException {
        stub = new OssHttpStub();
        stub.start();
        AliyunOssProperties props = new AliyunOssProperties("cn-hangzhou",
                "http://127.0.0.1:" + stub.port(), BUCKET,
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", null, 2000, 2000);
        AppProperties appProps = new AppProperties("dev", null,
                new AppProperties.Storage(null, BUCKET), null, null, null, null);
        oss = new OssProvidersConfig().ossClient(props, appProps);
        adapter = new OssStorageAdapter(oss, BUCKET);
    }

    @AfterEach
    void tearDown() {
        if (oss != null) {
            oss.shutdown();
        }
        if (stub != null) {
            stub.close();
        }
    }

    @Test
    @DisplayName("PUT wire：路径含 key，含 Content-Type/Content-Length/x-oss-meta-purpose/Authorization")
    void putWireFacts() {
        adapter.put(KEY, new ByteArrayInputStream(IMAGE), IMAGE.length, "image/png");

        OssHttpStub.Recorded put = stub.last("PUT");
        assertThat(put).isNotNull();
        assertThat(stub.pathStyleOrVirtualHostHasBucket(put)).isTrue();
        assertThat(put.path()).endsWith(KEY);
        assertThat(put.header("Content-Type")).isEqualTo("image/png");
        assertThat(put.header("Content-Length")).isEqualTo(String.valueOf(IMAGE.length));
        assertThat(put.header("x-oss-meta-purpose")).isEqualTo("assessment_source");
        assertThat(put.header("Authorization")).startsWith("OSS ");
        assertThat(new String(stub.object(KEY), StandardCharsets.UTF_8)).isEqualTo(
                new String(IMAGE, StandardCharsets.UTF_8));
    }

    @Test
    @DisplayName("GET 往返字节一致；exists=true；DELETE 后 exists=false")
    void roundTripExistsDelete() throws IOException {
        adapter.put(KEY, new ByteArrayInputStream(IMAGE), IMAGE.length, "image/png");
        assertThat(adapter.exists(KEY)).isTrue();

        try (InputStream in = adapter.getStream(KEY)) {
            assertThat(in).isNotNull();
            assertThat(in.readAllBytes()).isEqualTo(IMAGE);
        }
        assertThat(adapter.get(KEY)).isEqualTo(IMAGE);

        adapter.delete(KEY);
        assertThat(adapter.exists(KEY)).isFalse();
        assertThat(adapter.getStream(KEY)).isNull();
    }

    @Test
    @DisplayName("NoSuchKey(404) → getStream/get 返回 null，exists=false（不是依赖故障）")
    void noSuchKeyIsAbsentSemantics() {
        assertThat(adapter.getStream("dev/grant_face/missing")).isNull();
        assertThat(adapter.get("dev/grant_face/missing")).isNull();
        assertThat(adapter.exists("dev/grant_face/missing")).isFalse();
        // delete 幂等：不存在的 key 也成功。
        adapter.delete("dev/grant_face/missing");
    }

    @Test
    @DisplayName("AccessDenied(403) → 配置错误（不可重试，非 NoSuchKey）")
    void accessDeniedIsConfigurationFailure() {
        stub.forceError(403, "AccessDenied");
        assertThatThrownBy(() -> adapter.getStream(KEY))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> {
                    ApiException api = (ApiException) thrown;
                    assertThat(api.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
                    assertThat(api.getHttpStatus()).isEqualTo(503);
                    assertThat(api.isRetryable()).isFalse();
                    assertThat(api.getMessage()).contains("configuration error").contains("AccessDenied");
                });
    }

    @Test
    @DisplayName("服务端 5xx → 依赖故障（可重试）")
    void serverErrorIsDependencyFailure() {
        stub.forceError(500, "InternalError");
        assertThatThrownBy(() -> adapter.getStream(KEY))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> {
                    ApiException api = (ApiException) thrown;
                    assertThat(api.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
                    assertThat(api.isRetryable()).isTrue();
                    assertThat(api.getMessage()).contains("dependency failure");
                });
    }

    @Test
    @DisplayName("不可达 endpoint → ClientException → 依赖故障（可重试），不静默成功/不回退本地")
    void unreachableEndpointIsDependencyFailure() {
        AliyunOssProperties props = new AliyunOssProperties("cn-hangzhou",
                "http://127.0.0.1:1", BUCKET,
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", null, 1000, 1000);
        AppProperties appProps = new AppProperties("dev", null,
                new AppProperties.Storage(null, BUCKET), null, null, null, null);
        OSS unreachable = new OssProvidersConfig().ossClient(props, appProps);
        try {
            OssStorageAdapter broken = new OssStorageAdapter(unreachable, BUCKET);
            assertThatThrownBy(() -> broken.put(KEY, new ByteArrayInputStream(IMAGE), IMAGE.length, "image/png"))
                    .isInstanceOf(ApiException.class)
                    .satisfies(thrown -> assertThat(((ApiException) thrown).isRetryable()).isTrue());
        } finally {
            unreachable.shutdown();
        }
    }

    @Test
    @DisplayName("日志与异常消息不含 AK/SK/token（Logback ListAppender）")
    void logsAndMessagesDoNotContainSecrets() {
        ch.qos.logback.classic.Logger logger =
                (ch.qos.logback.classic.Logger) org.slf4j.LoggerFactory.getLogger(OssStorageAdapter.class);
        ch.qos.logback.core.read.ListAppender<ch.qos.logback.classic.spi.ILoggingEvent> appender =
                new ch.qos.logback.core.read.ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            stub.forceError(403, "AccessDenied");
            ApiException failure = (ApiException) org.assertj.core.api.Assertions
                    .catchThrowable(() -> adapter.getStream(KEY));
            assertThat(failure.getMessage())
                    .doesNotContain("LTAI-FAKE-DO-NOT-USE")
                    .doesNotContain("FAKE-SECRET-DO-NOT-USE");
            for (ch.qos.logback.classic.spi.ILoggingEvent event : appender.list) {
                assertThat(event.getFormattedMessage())
                        .doesNotContain("LTAI-FAKE-DO-NOT-USE")
                        .doesNotContain("FAKE-SECRET-DO-NOT-USE");
            }
        } finally {
            logger.detachAppender(appender);
        }
    }

    /** 最小 OSS HTTP stub（本机随机端口；路径式选址）。 */
    private static final class OssHttpStub implements AutoCloseable {

        record Recorded(String method, String path, Map<String, List<String>> headers) {
            String header(String name) {
                for (Map.Entry<String, List<String>> e : headers.entrySet()) {
                    if (e.getKey().equalsIgnoreCase(name)) {
                        return e.getValue().isEmpty() ? null : e.getValue().get(0);
                    }
                }
                return null;
            }
        }

        private final Map<String, byte[]> objects = new ConcurrentHashMap<>();
        private final List<Recorded> requests = new CopyOnWriteArrayList<>();
        private final AtomicInteger forcedStatus = new AtomicInteger(0);
        private final java.util.concurrent.atomic.AtomicReference<String> forcedCode =
                new java.util.concurrent.atomic.AtomicReference<>("");
        private HttpServer server;

        void start() throws IOException {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", this::handle);
            server.start();
        }

        int port() {
            return server.getAddress().getPort();
        }

        void forceError(int status, String code) {
            forcedStatus.set(status);
            forcedCode.set(code);
        }

        byte[] object(String key) {
            return objects.get(key);
        }

        Recorded last(String method) {
            for (int i = requests.size() - 1; i >= 0; i--) {
                if (requests.get(i).method().equalsIgnoreCase(method)) {
                    return requests.get(i);
                }
            }
            return null;
        }

        boolean pathStyleOrVirtualHostHasBucket(Recorded recorded) {
            String path = recorded.path();
            String host = recorded.header("Host");
            return path.startsWith("/" + BUCKET + "/") || (host != null && host.startsWith(BUCKET + "."));
        }

        private void handle(HttpExchange exchange) throws IOException {
            String path = exchange.getRequestURI().getPath();
            byte[] body = exchange.getRequestBody().readAllBytes();
            requests.add(new Recorded(exchange.getRequestMethod(), path, exchange.getRequestHeaders()));
            String key = keyOf(path);

            int forced = forcedStatus.get();
            if (forced > 0) {
                error(exchange, forced, forcedCode.get(), "forced");
                return;
            }
            switch (exchange.getRequestMethod().toUpperCase(java.util.Locale.ROOT)) {
                case "PUT" -> {
                    objects.put(key, body);
                    exchange.getResponseHeaders().set("ETag", "\"fake-etag\"");
                    exchange.getResponseHeaders().set("x-oss-request-id", "req-put");
                    exchange.sendResponseHeaders(200, -1);
                }
                case "GET" -> {
                    byte[] stored = objects.get(key);
                    if (stored == null) {
                        error(exchange, 404, "NoSuchKey", "key not found");
                        return;
                    }
                    exchange.getResponseHeaders().set("Content-Type", "image/png");
                    exchange.getResponseHeaders().set("x-oss-request-id", "req-get");
                    exchange.sendResponseHeaders(200, stored.length);
                    exchange.getResponseBody().write(stored);
                }
                case "HEAD" -> {
                    byte[] stored = objects.get(key);
                    if (stored == null) {
                        exchange.sendResponseHeaders(404, -1);
                        return;
                    }
                    exchange.getResponseHeaders().set("Content-Type", "image/png");
                    exchange.getResponseHeaders().set("Content-Length", String.valueOf(stored.length));
                    exchange.sendResponseHeaders(200, -1);
                }
                case "DELETE" -> {
                    objects.remove(key);
                    exchange.sendResponseHeaders(204, -1);
                }
                default -> error(exchange, 400, "InvalidRequest", "unsupported");
            }
            exchange.close();
        }

        private String keyOf(String path) {
            String trimmed = path.startsWith("/") ? path.substring(1) : path;
            String prefix = BUCKET + "/";
            return trimmed.startsWith(prefix) ? trimmed.substring(prefix.length()) : trimmed;
        }

        private void error(HttpExchange exchange, int status, String code, String message)
                throws IOException {
            byte[] xml = ("<Error><Code>" + code + "</Code><Message>" + message
                    + "</Message><RequestId>req-error</RequestId><HostId>fake-host</HostId></Error>")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/xml");
            exchange.getResponseHeaders().set("x-oss-request-id", "req-error");
            exchange.sendResponseHeaders(status, xml.length);
            exchange.getResponseBody().write(xml);
            exchange.close();
        }

        @Override
        public void close() {
            if (server != null) {
                server.stop(0);
            }
        }
    }
}

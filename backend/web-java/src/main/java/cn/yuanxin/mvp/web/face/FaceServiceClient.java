package cn.yuanxin.mvp.web.face;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

/**
 * InsightFace 人脸服务的 HTTP 客户端（B 自有；使用 Spring {@code RestClient}，不新增依赖）。
 *
 * <p>仅封装只读/无副作用端点：{@code GET /v1/health}、{@code POST /v1/extract}、
 * {@code POST /v1/verify}。<b>绝不</b>调用 {@code /v1/namespaces/**} 的注册/删除端点。</p>
 *
 * <p><b>失败语义</b>：非 2xx 解析服务错误信封为 {@link FaceServiceError} 并抛
 * {@link FaceServiceException}（携带 {@link FaceServiceFailureKind}）；网络异常/超时归类为
 * DEPENDENCY。<b>绝不</b>把失败当作成功。日志只记 op、HTTP 状态、服务码与 request_id；
 * 绝不记 token、图像字节或 embedding。</p>
 */
public class FaceServiceClient {

    private static final Logger log = LoggerFactory.getLogger(FaceServiceClient.class);

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public FaceServiceClient(InsightFaceProperties properties, ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(properties.connectTimeoutMillis());
        requestFactory.setReadTimeout(properties.readTimeoutMillis());
        RestClient.Builder builder = RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory);
        String token = properties.resolvedToken();
        if (token != null) {
            builder = builder.defaultHeader("X-Internal-Token", token);
        }
        this.restClient = builder.build();
    }

    /** {@code GET /v1/health}（公开）。 */
    public Health health() {
        String body = exchange(() -> restClient.get().uri("/v1/health").retrieve().body(String.class),
                "health");
        try {
            JsonNode root = objectMapper.readTree(body);
            JsonNode liveness = root.path("liveness");
            return new Health("ok".equalsIgnoreCase(root.path("status").asText()),
                    root.path("model_version").asText(null),
                    root.path("model_loaded").asBoolean(false),
                    liveness.path("supported").asBoolean(false));
        } catch (Exception malformed) {
            throw new FaceServiceException(new FaceServiceError(null,
                    "malformed health response", false, null, 200));
        }
    }

    /** {@code POST /v1/extract}（multipart 字段名 {@code image}；零写入）。 */
    public ExtractResult extract(byte[] image) {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("image", imagePart(image)).contentType(MediaType.APPLICATION_OCTET_STREAM);
        String body = exchange(() -> restClient.post().uri("/v1/extract")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(builder.build())
                .retrieve().body(String.class), "extract");
        try {
            JsonNode root = objectMapper.readTree(body);
            return new ExtractResult(root.path("face_count").asInt(0),
                    root.path("request_id").asText(null));
        } catch (Exception malformed) {
            throw new FaceServiceException(new FaceServiceError(null,
                    "malformed extract response", false, null, 200));
        }
    }

    /** {@code POST /v1/verify}（multipart image + namespace + subject_id，可选 threshold）。 */
    public VerifyResult verify(byte[] image, String namespace, String subjectId, Double threshold) {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("image", imagePart(image)).contentType(MediaType.APPLICATION_OCTET_STREAM);
        builder.part("namespace", namespace);
        builder.part("subject_id", subjectId);
        if (threshold != null) {
            builder.part("threshold", Double.toString(threshold));
        }
        String body = exchange(() -> restClient.post().uri("/v1/verify")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(builder.build())
                .retrieve().body(String.class), "verify");
        try {
            JsonNode root = objectMapper.readTree(body);
            JsonNode thresholdNode = root.path("threshold");
            return new VerifyResult(root.path("matched").asBoolean(false),
                    root.path("similarity").asDouble(Double.NaN),
                    thresholdNode.isMissingNode() || thresholdNode.isNull()
                            ? null : thresholdNode.asDouble(),
                    root.path("request_id").asText(null));
        } catch (Exception malformed) {
            throw new FaceServiceException(new FaceServiceError(null,
                    "malformed verify response", false, null, 200));
        }
    }

    private static ByteArrayResource imagePart(byte[] image) {
        return new ByteArrayResource(image) {
            @Override
            public String getFilename() {
                return "image";
            }
        };
    }

    private String exchange(java.util.function.Supplier<String> call, String operation) {
        try {
            return call.get();
        } catch (RestClientResponseException httpFailure) {
            throw toException(httpFailure, operation);
        } catch (RestClientException transportFailure) {
            log.warn("face service transport failure op={} exception={}",
                    operation, transportFailure.getClass().getSimpleName());
            throw new FaceServiceException(new FaceServiceError(null,
                    transportFailure.getClass().getSimpleName(), true, null, 0));
        }
    }

    private FaceServiceException toException(RestClientResponseException httpFailure, String operation) {
        int status = httpFailure.getStatusCode().value();
        String code = null;
        String message = null;
        boolean retryable = false;
        String requestId = null;
        try {
            JsonNode error = objectMapper.readTree(httpFailure.getResponseBodyAsString()).path("error");
            if (!error.isMissingNode()) {
                code = error.path("code").asText(null);
                message = error.path("message").asText(null);
                retryable = error.path("retryable").asBoolean(false);
                requestId = error.path("request_id").asText(null);
            }
        } catch (Exception unparseable) {
            message = "unparseable error body";
        }
        log.warn("face service call failed op={} http={} code={} requestId={}",
                operation, status, code == null ? "<none>" : code, requestId == null ? "<none>" : requestId);
        return new FaceServiceException(new FaceServiceError(code, message, retryable, requestId, status));
    }

    public record Health(boolean ok, String modelVersion, boolean modelLoaded, boolean livenessSupported) {
    }

    public record ExtractResult(int faceCount, String requestId) {
    }

    public record VerifyResult(boolean matched, double similarity, Double threshold, String requestId) {
    }
}

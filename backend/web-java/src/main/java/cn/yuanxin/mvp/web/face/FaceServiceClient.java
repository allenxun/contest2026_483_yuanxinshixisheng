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

    /**
     * {@code POST /v1/verify}（multipart image + namespace + subject_id + <b>恒定</b>
     * {@code require_liveness=true}，可选 threshold）。
     *
     * <p><b>BLOCKER 1（红线：护理 1:1 必须要求活体）</b>：{@code require_liveness=true}
     * <b>恒定发送、不可配置、无关闭开关</b>——设置可削弱安全的开关不可接受。当前已部署服务
     * 未实现活体，会返回 501 {@code LIVENESS_UNSUPPORTED}，上层映射
     * {@code CAPABILITY_UNAVAILABLE}（503）；这是刻意 fail-closed，不是缺陷。
     * {@code /v1/extract}（{@code classify} 路径）<b>不</b>加该门：服务端 extract 无此门，
     * 且 {@code classify} 永不 MATCHED（见 {@code InsightFaceProvider}）。</p>
     *
     * <p><b>SUGGESTION 9（严格契约，绝不静默降级）</b>：2xx 响应必须满足：
     * {@code matched} 存在且为 JSON boolean；{@code similarity}/{@code threshold} 存在且为
     * <b>有限</b>数值；{@code liveness} 段存在且 {@code supported} 为 JSON boolean；
     * 若返回 {@code subject_id} 必须与请求值相等。任一不符 ⇒ 抛 {@link FaceServiceException}
     * （契约/依赖失败，映射 {@code DEPENDENCY_FAILED}），<b>绝不</b>默认成 MATCHED/MISMATCH。</p>
     *
     * <p><b>活体 fail-closed（红线加固）</b>：既然请求已要求活体，2xx 响应若声称
     * {@code liveness.supported=false} 即为矛盾——按 501 {@code LIVENESS_UNSUPPORTED}
     * 处理（映射 {@code CAPABILITY_UNAVAILABLE}），<b>绝不</b>因 {@code matched=true} 而放行。
     * 这堵住"服务忽略 {@code require_liveness} 却返回 matched"的伪完成路径。</p>
     */
    public VerifyResult verify(byte[] image, String namespace, String subjectId, Double threshold) {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("image", imagePart(image)).contentType(MediaType.APPLICATION_OCTET_STREAM);
        builder.part("namespace", namespace);
        builder.part("subject_id", subjectId);
        // 恒定要求活体；无成员/配置可关闭此门。
        builder.part("require_liveness", "true");
        if (threshold != null) {
            builder.part("threshold", Double.toString(threshold));
        }
        String body = exchange(() -> restClient.post().uri("/v1/verify")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(builder.build())
                .retrieve().body(String.class), "verify");
        return parseVerifyResponse(body, subjectId);
    }

    /** 严格校验 verify 响应形状；任何缺失/类型不符都 fail-closed，不降级为 MATCHED/MISMATCH。 */
    private VerifyResult parseVerifyResponse(String body, String requestedSubjectId) {
        JsonNode root;
        try {
            root = objectMapper.readTree(body);
        } catch (Exception unparseable) {
            throw malformedVerify("response is not valid JSON", null);
        }
        if (root == null || !root.isObject()) {
            throw malformedVerify("response is not a JSON object", null);
        }
        String requestId = root.path("request_id").asText(null);

        JsonNode matchedNode = root.get("matched");
        if (matchedNode == null || !matchedNode.isBoolean()) {
            throw malformedVerify("'matched' must be a JSON boolean", requestId);
        }
        double similarity = requireFiniteNumber(root, "similarity", requestId);
        double threshold = requireFiniteNumber(root, "threshold", requestId);

        JsonNode livenessNode = root.get("liveness");
        if (livenessNode == null || !livenessNode.isObject()) {
            throw malformedVerify("'liveness' block must be an object", requestId);
        }
        JsonNode supportedNode = livenessNode.get("supported");
        if (supportedNode == null || !supportedNode.isBoolean()) {
            throw malformedVerify("'liveness.supported' must be a JSON boolean", requestId);
        }
        if (!supportedNode.booleanValue()) {
            // 请求已要求活体，2xx 却声明不支持：矛盾，fail-closed（绝不因 matched 放行）。
            log.warn("face service verify reports liveness unsupported despite require_liveness=true"
                    + " requestId={}", requestId == null ? "<none>" : requestId);
            throw new FaceServiceException(new FaceServiceError("LIVENESS_UNSUPPORTED",
                    "required liveness was not supported by the service", false, requestId, 501));
        }

        JsonNode subjectNode = root.get("subject_id");
        if (subjectNode != null && !subjectNode.isNull()) {
            if (!subjectNode.isTextual() || requestedSubjectId == null
                    || !requestedSubjectId.equals(subjectNode.textValue())) {
                throw malformedVerify("'subject_id' echo does not match the requested subject", requestId);
            }
        }
        return new VerifyResult(matchedNode.booleanValue(), similarity, threshold, requestId);
    }

    private double requireFiniteNumber(JsonNode root, String field, String requestId) {
        JsonNode node = root.get(field);
        if (node == null || !node.isNumber() || !Double.isFinite(node.doubleValue())) {
            throw malformedVerify("'" + field + "' must be a finite number", requestId);
        }
        return node.doubleValue();
    }

    private FaceServiceException malformedVerify(String detail, String requestId) {
        log.warn("face service verify contract violation detail={} requestId={}",
                detail, requestId == null ? "<none>" : requestId);
        return new FaceServiceException(new FaceServiceError("MALFORMED_RESPONSE",
                "malformed verify response: " + detail, false, requestId, 200));
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

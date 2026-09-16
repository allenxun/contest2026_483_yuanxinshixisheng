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

import java.util.List;
import java.util.Optional;

/**
 * InsightFace 人脸服务的 HTTP 客户端，也是 {@link FaceIdentityPort} 的当前唯一实现载体
 * （B 自有；使用 Spring {@code RestClient}，不新增依赖）。
 *
 * <p>封装：{@code GET /v1/health}、{@code POST /v1/extract}、{@code POST /v1/quality}、
 * {@code POST /v1/verify}（两种语义，见下）、{@code POST /v1/namespaces/{ns}/search}（只读 1:N）、
 * 以及 {@code POST/GET/DELETE /v1/namespaces/{ns}/subjects...}（写/读主体）。
 * 注册与删除的 HTTP 能力<b>已实现且已测试</b>，但<b>尚无业务流程调用</b>——成员建档的唯一生产写入方
 * 仍是 D 包 Python，属跨包写域；精确 blocker 与协调接口见
 * {@code backend/handoffs/B-face-java.md} 与 {@link FaceIdentityPort#register} 的 javadoc。</p>
 *
 * <p><b>两种 verify 语义在类型层面分离</b>：{@link #verifyPhotoOnly} 返回
 * {@link PhotoComparisonMatch}（<b>照片比对，无防翻拍能力；不得用于护理准入</b>），
 * {@link #verifyWithLiveness} 返回 {@link LivenessVerifiedMatch}（恒发 {@code require_liveness=true}）。
 * 混用会<b>编译失败</b>，这是刻意设计。</p>
 *
 * <p><b>失败语义（fail-closed）</b>：非 2xx 解析服务错误信封为 {@link FaceServiceError} 并抛
 * {@link FaceServiceException}；网络异常/超时归类 DEPENDENCY；2xx 响应形状不符冻结契约
 * （必需键缺失、类型不符、数值非有限、{@code subject_id} 回显不一致）⇒ 抛
 * {@code MALFORMED_RESPONSE}（DEPENDENCY）。<b>绝不</b>把失败当作成功，<b>绝不</b>回退替身，
 * <b>绝不</b>返回"看似成功"的默认值。</p>
 *
 * <p><b>日志纪律</b>：只记 op、HTTP 状态、服务码与 {@code request_id}；<b>绝不</b>记 token、
 * 图片字节/base64、embedding、namespace 取值、{@code subjectRef} 取值或候选/相似度明细。</p>
 */
public class FaceServiceClient implements FaceIdentityPort {

    private static final Logger log = LoggerFactory.getLogger(FaceServiceClient.class);

    private final RestClient restClient;
    private final ObjectMapper objectMapper;
    private final String namespace;
    private final Double verifyThreshold;

    public FaceServiceClient(InsightFaceProperties properties, ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.namespace = properties.namespace();
        this.verifyThreshold = properties.verifyThreshold();
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

    @Override
    public String identityNamespace() {
        return namespace;
    }

    /**
     * {@code GET /v1/health}（公开）。严格解析：{@code status}/{@code model_version} 为文本、
     * {@code model_loaded} 为 JSON boolean、{@code liveness.supported} 为 JSON boolean、
     * {@code library_revision} 为整数；任一不符 ⇒ {@code MALFORMED_RESPONSE}。
     * {@code livenessSupported} 如实取自服务端，绝不硬编码 true。
     */
    @Override
    public FaceHealthView health() {
        String body = exchange(() -> restClient.get().uri("/v1/health").retrieve().body(String.class),
                "health");
        JsonNode root = readObject(body, "health");
        String requestId = textOrNull(root, "request_id");
        String status = requireText(root, "status", "health", requestId);
        String modelVersion = requireText(root, "model_version", "health", requestId);
        boolean modelLoaded = requireBoolean(root, "model_loaded", "health", requestId);
        JsonNode liveness = root.get("liveness");
        if (liveness == null || !liveness.isObject()) {
            throw malformed("health", "'liveness' block must be an object", requestId);
        }
        boolean livenessSupported = requireBoolean(liveness, "supported", "health", requestId);
        long libraryRevision = requireIntegralNumber(root, "library_revision", "health", requestId);
        return new FaceHealthView(status, modelVersion, modelLoaded, livenessSupported, libraryRevision);
    }

    /**
     * {@code POST /v1/extract}（multipart 字段名 {@code image}；零写入）。
     *
     * @param purpose 仅用于审计分类，绝不作为身份信息；当前不发送到服务端（服务端 extract 无该参数）
     */
    @Override
    public FaceExtractView extract(String purpose, byte[] image) {
        String body = exchange(() -> restClient.post().uri("/v1/extract")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(imageMultipart(image).build())
                .retrieve().body(String.class), "extract");
        JsonNode root = readObject(body, "extract");
        String requestId = textOrNull(root, "request_id");
        return new FaceExtractView(requireFaceCount(root, "extract", requestId), requestId);
    }

    /**
     * {@code POST /v1/quality}（multipart 字段名 {@code image}；零写入）。
     * 严格校验 {@code face_count}、非空 {@code faces}、所选人脸的质量块与顶层
     * {@code liveness.supported}；{@code minAcceptable} 取最大人脸的质量判定。
     * {@code reasons} 由服务端未提供聚合原因，诚实返回空列表（绝不用相似度/检测分数冒充）。
     */
    @Override
    public FaceQualityView quality(String purpose, byte[] image) {
        String body = exchange(() -> restClient.post().uri("/v1/quality")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(imageMultipart(image).build())
                .retrieve().body(String.class), "quality");
        JsonNode root = readObject(body, "quality");
        String requestId = textOrNull(root, "request_id");
        int faceCount = requireFaceCount(root, "quality", requestId);
        JsonNode faces = root.get("faces");
        if (faces == null || !faces.isArray() || faces.isEmpty()) {
            throw malformed("quality", "'faces' must be a non-empty array", requestId);
        }
        JsonNode liveness = root.get("liveness");
        if (liveness == null || !liveness.isObject()) {
            throw malformed("quality", "'liveness' block must be an object", requestId);
        }
        boolean livenessSupported = requireBoolean(liveness, "supported", "quality", requestId);

        int selected = 0;
        for (int i = 0; i < faces.size(); i++) {
            JsonNode face = faces.get(i);
            if (face != null && face.isObject() && face.path("largest_face").asBoolean(false)) {
                selected = i;
                break;
            }
        }
        JsonNode face = faces.get(selected);
        if (face == null || !face.isObject()) {
            throw malformed("quality", "'faces' entries must be objects", requestId);
        }
        JsonNode qualityBlock = face.get("quality");
        if (qualityBlock == null || !qualityBlock.isObject()) {
            throw malformed("quality", "selected face must carry a 'quality' block", requestId);
        }
        boolean minAcceptable = requireBoolean(qualityBlock, "min_acceptable", "quality", requestId);
        return new FaceQualityView(faceCount, minAcceptable, List.of(), livenessSupported, requestId);
    }

    /**
     * namespace 限定的只读 1:N 搜索（{@code POST /v1/namespaces/{ns}/search}）。
     *
     * <p>请求复用 extract/verify 的 multipart {@code image} 构造方式；<b>不传</b> {@code top_k}，
     * <b>绝不</b>传任何阈值（服务端固定策略）。响应严格校验：{@code decision} 取值合法、
     * {@code policy_version}/{@code request_id} 为文本、{@code library_revision} 为整数；
     * {@code matched} 时还需非空 {@code subject_id} 与有限 {@code similarity}；
     * <b>非 matched 却带 {@code subject_id}</b>（含 null）视为契约违规 ⇒ {@code MALFORMED_RESPONSE}。
     *
     * <p>映射保守：{@code no_match}/{@code uncertain} 一律 <b>不</b>返回 {@code subjectRef}
     * （构造器强制），且 {@code NO_MATCH} <b>不得</b>被解释为可靠新人。
     */
    @Override
    public FaceSearchResult search(String purpose, byte[] image) {
        String body = exchange(() -> restClient.post()
                .uri("/v1/namespaces/{namespace}/search", namespace)
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(imageMultipart(image).build())
                .retrieve().body(String.class), "search");
        JsonNode root = readObject(body, "search");
        String requestId = requireText(root, "request_id", "search", null);
        String policyVersion = requireText(root, "policy_version", "search", requestId);
        long libraryRevision = requireIntegralNumber(root, "library_revision", "search", requestId);
        String decisionRaw = requireText(root, "decision", "search", requestId);

        if ("matched".equals(decisionRaw)) {
            String subjectRef = requireText(root, "subject_id", "search", requestId);
            double similarity = requireFiniteNumber(root, "similarity", "search", requestId);
            return new FaceSearchResult(FaceSearchDecision.MATCHED, subjectRef, similarity,
                    policyVersion, libraryRevision, requestId);
        }
        if (!"no_match".equals(decisionRaw) && !"uncertain".equals(decisionRaw)) {
            throw malformed("search", "unknown 'decision' value", requestId);
        }
        if (root.has("subject_id")) {
            // 服务端契约禁止非 matched 携带 subject_id；出现即形状违规，绝不当作身份泄漏容忍。
            throw malformed("search", "non-matched decision must not carry 'subject_id'", requestId);
        }
        FaceSearchDecision decision = "no_match".equals(decisionRaw)
                ? FaceSearchDecision.NO_MATCH : FaceSearchDecision.UNCERTAIN;
        return new FaceSearchResult(decision, null, null, policyVersion, libraryRevision, requestId);
    }

    /**
     * {@code POST /v1/verify} <b>无活体</b>照片比对（<b>照片比对，无防翻拍能力</b>）。
     *
     * <p>请求<b>不</b>携带 {@code require_liveness}（因此不会触发服务端 501）；响应严格校验
     * {@code matched}（JSON boolean）、{@code similarity}/{@code threshold}（有限数值）与
     * {@code subject_id} 回显。结果<b>不得</b>用于护理准入（只接受
     * {@link LivenessVerifiedMatch}）；不得用于任何要求现场性的场景。
     */
    @Override
    public PhotoComparisonMatch verifyPhotoOnly(String purpose, String subjectRef, byte[] image) {
        VerifyOutcome outcome = doVerify(subjectRef, image, false, "verifyPhotoOnly");
        return new PhotoComparisonMatch(outcome.matched, outcome.similarity, outcome.threshold,
                subjectRef, outcome.requestId);
    }

    /**
     * {@code POST /v1/verify} <b>要求活体</b>的 1:1：恒发 {@code require_liveness=true}，
     * <b>无关闭开关</b>。语义与既有 {@code verify(...)} <b>逐字一致</b>：
     * {@code liveness.supported=false} ⇒ 501 {@code LIVENESS_UNSUPPORTED}；
     * {@code supported=true} 时还须本次样本 {@code liveness.passed} 为 JSON boolean 且为 true，
     * 否则 501 {@code LIVENESS_NOT_PASSED}。当前真实服务无活体 ⇒ 恒抛异常，
     * 护理路径映射 {@code CAPABILITY_UNAVAILABLE}（刻意 fail-closed，不是缺陷）。
     *
     * <p>阈值沿用配置 {@code app.face.insightface.verify-threshold}（若配置存在则随请求发送）；
     * {@code require_liveness} 与其它字段无关，恒为 true。
     */
    @Override
    public LivenessVerifiedMatch verifyWithLiveness(String purpose, String subjectRef, byte[] image) {
        VerifyOutcome outcome = doVerify(subjectRef, image, true, "verifyWithLiveness");
        return new LivenessVerifiedMatch(outcome.matched, outcome.similarity, outcome.threshold,
                subjectRef, outcome.requestId);
    }

    /**
     * 登记主体（{@code POST /v1/namespaces/{ns}/subjects}；写操作）。
     *
     * <p>{@code subjectRef} 由调用方<b>预先确定</b>并作为 {@code subject_id} 发送（不由服务端随机生成）；
     * 显式发送 {@code on_exists=conflict}，使既有主体<b>绝不</b>被静默覆盖
     * （与端口声明的 {@code SUBJECT_ALREADY_EXISTS} 语义一致，也不受部署端
     * {@code register_on_exists=overwrite} 影响）。响应严格校验 {@code subject_id} 回显、
     * {@code created_at} 与 {@code library_revision}。</p>
     *
     * <p><b>当前状态：能力已实现且已测试，但尚无业务流程调用。</b>成员建档（T01 {@code members}）
     * 的唯一生产写入方仍是 D 包 Python {@code identity.enroll}，属跨包写域；接入前必须由总协调裁定
     * （见 {@code backend/handoffs/B-face-java.md}）。</p>
     */
    @Override
    public FaceSubjectRegistration register(String purpose, String subjectRef, byte[] referenceImage) {
        String body = exchange(() -> restClient.post()
                .uri("/v1/namespaces/{namespace}/subjects", namespace)
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(subjectMultipart(subjectRef, referenceImage).build())
                .retrieve().body(String.class), "register");
        JsonNode root = readObject(body, "register");
        String requestId = textOrNull(root, "request_id");
        String echoed = requireText(root, "subject_id", "register", requestId);
        if (!echoed.equals(subjectRef)) {
            throw malformed("register", "'subject_id' echo does not match the requested subject", requestId);
        }
        String createdAt = requireText(root, "created_at", "register", requestId);
        long libraryRevision = requireIntegralNumber(root, "library_revision", "register", requestId);
        return new FaceSubjectRegistration(subjectRef, libraryRevision, createdAt, requestId);
    }

    /**
     * 只读查询主体（{@code GET /v1/namespaces/{ns}/subjects/{id}}），用于登记超时后的对账。
     *
     * <p>404（{@code SUBJECT_NOT_FOUND} 或 {@code NAMESPACE_NOT_FOUND}）⇒ {@link Optional#empty()}
     * （<b>不</b>抛）；其余错误照常抛出。响应严格校验 {@code subject_id} 回显、{@code created_at}
     * 与 {@code library_revision}。
     */
    @Override
    public Optional<FaceSubjectView> get(String subjectRef) {
        String body;
        try {
            body = exchange(() -> restClient.get()
                    .uri("/v1/namespaces/{namespace}/subjects/{subject}", namespace, subjectRef)
                    .retrieve().body(String.class), "get");
        } catch (FaceServiceException failure) {
            if (isNotFound(failure)) {
                return Optional.empty();
            }
            throw failure;
        }
        JsonNode root = readObject(body, "get");
        String requestId = textOrNull(root, "request_id");
        String echoed = requireText(root, "subject_id", "get", requestId);
        if (!echoed.equals(subjectRef)) {
            throw malformed("get", "'subject_id' echo does not match the requested subject", requestId);
        }
        String createdAt = requireText(root, "created_at", "get", requestId);
        long libraryRevision = requireIntegralNumber(root, "library_revision", "get", requestId);
        return Optional.of(new FaceSubjectView(subjectRef, createdAt, libraryRevision));
    }

    /**
     * 删除主体（{@code DELETE /v1/namespaces/{ns}/subjects/{id}}；写操作）。
     *
     * <p><b>重复删除幂等</b>：服务端对已不存在的主体返回 404 {@code SUBJECT_NOT_FOUND}；
     * 本实现不抛异常，而是返回 {@link FaceSubjectDeletion}({@code deleted=false})，并如实把
     * {@code libraryRevision} 标为 {@link FaceSubjectDeletion#UNKNOWN_LIBRARY_REVISION}
     * （404 信封不携带修订号）。删除算法主体<b>不</b>隐式撤销授权、也<b>不</b>删除业务成员行。</p>
     */
    @Override
    public FaceSubjectDeletion delete(String subjectRef) {
        String body;
        try {
            body = exchange(() -> restClient.delete()
                    .uri("/v1/namespaces/{namespace}/subjects/{subject}", namespace, subjectRef)
                    .retrieve().body(String.class), "delete");
        } catch (FaceServiceException failure) {
            if (isNotFound(failure)) {
                return new FaceSubjectDeletion(false,
                        FaceSubjectDeletion.UNKNOWN_LIBRARY_REVISION, failure.error().requestId());
            }
            throw failure;
        }
        JsonNode root = readObject(body, "delete");
        String requestId = textOrNull(root, "request_id");
        boolean deleted = requireBoolean(root, "deleted", "delete", requestId);
        long libraryRevision = requireIntegralNumber(root, "library_revision", "delete", requestId);
        return new FaceSubjectDeletion(deleted, libraryRevision, requestId);
    }

    // ------------------------------------------------------------------
    // verify internals
    // ------------------------------------------------------------------

    private VerifyOutcome doVerify(String subjectRef, byte[] image, boolean requireLiveness,
                                   String operation) {
        MultipartBodyBuilder builder = imageMultipart(image);
        builder.part("namespace", namespace);
        builder.part("subject_id", subjectRef);
        if (requireLiveness) {
            // 恒定要求活体；无成员/配置可关闭此门（无"跳过活体"开关）。
            builder.part("require_liveness", "true");
        }
        if (verifyThreshold != null) {
            builder.part("threshold", Double.toString(verifyThreshold));
        }
        String body = exchange(() -> restClient.post().uri("/v1/verify")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(builder.build())
                .retrieve().body(String.class), operation);
        return parseVerifyResponse(body, subjectRef, requireLiveness, operation);
    }

    /**
     * 严格校验 verify 响应形状；任何缺失/类型不符都 fail-closed，不降级为 MATCHED/MISMATCH。
     * {@code requireLiveness=true} 时追加活体 fail-closed（语义与既有 verify 逐字一致）。
     */
    private VerifyOutcome parseVerifyResponse(String body, String requestedSubjectId,
                                              boolean requireLiveness, String operation) {
        JsonNode root = readObject(body, operation);
        String requestId = textOrNull(root, "request_id");

        boolean matched = requireBoolean(root, "matched", operation, requestId);
        double similarity = requireFiniteNumber(root, "similarity", operation, requestId);
        double threshold = requireFiniteNumber(root, "threshold", operation, requestId);

        if (requireLiveness) {
            JsonNode livenessNode = root.get("liveness");
            if (livenessNode == null || !livenessNode.isObject()) {
                throw malformed(operation, "'liveness' block must be an object", requestId);
            }
            boolean supported = requireBoolean(livenessNode, "supported", operation, requestId);
            if (!supported) {
                // 请求已要求活体，2xx 却声明不支持：矛盾，fail-closed（绝不因 matched 放行）。
                log.warn("face service {} reports liveness unsupported despite require_liveness=true"
                        + " requestId={}", operation, requestId == null ? "<none>" : requestId);
                throw new FaceServiceException(new FaceServiceError("LIVENESS_UNSUPPORTED",
                        "required liveness was not supported by the service", false, requestId, 501));
            }
            // 契约冻结：supported=true 还须本次样本 passed=true（缺失/非 boolean/false 一律拒绝）。
            JsonNode passedNode = livenessNode.get("passed");
            if (passedNode == null || !passedNode.isBoolean() || !passedNode.booleanValue()) {
                log.warn("face service {} liveness not passed (fieldPresent={}, boolean={}) requestId={}",
                        operation, passedNode != null, passedNode != null && passedNode.isBoolean(),
                        requestId == null ? "<none>" : requestId);
                throw new FaceServiceException(new FaceServiceError("LIVENESS_NOT_PASSED",
                        "required liveness was not passed for this sample", false, requestId, 501));
            }
        }

        JsonNode subjectNode = root.get("subject_id");
        if (subjectNode != null && !subjectNode.isNull()) {
            if (!subjectNode.isTextual() || requestedSubjectId == null
                    || !requestedSubjectId.equals(subjectNode.textValue())) {
                throw malformed(operation,
                        "'subject_id' echo does not match the requested subject", requestId);
            }
        }
        return new VerifyOutcome(matched, similarity, threshold, requestId);
    }

    // ------------------------------------------------------------------
    // parsing helpers (strict; every violation => MALFORMED_RESPONSE)
    // ------------------------------------------------------------------

    private JsonNode readObject(String body, String operation) {
        JsonNode root;
        try {
            root = objectMapper.readTree(body);
        } catch (Exception unparseable) {
            throw malformed(operation, "response is not valid JSON", null);
        }
        if (root == null || !root.isObject()) {
            throw malformed(operation, "response is not a JSON object", null);
        }
        return root;
    }

    private String requireText(JsonNode root, String field, String operation, String requestId) {
        JsonNode node = root.get(field);
        if (node == null || !node.isTextual() || node.textValue().isBlank()) {
            throw malformed(operation, "'" + field + "' must be a non-blank string", requestId);
        }
        return node.textValue();
    }

    private boolean requireBoolean(JsonNode root, String field, String operation, String requestId) {
        JsonNode node = root.get(field);
        if (node == null || !node.isBoolean()) {
            throw malformed(operation, "'" + field + "' must be a JSON boolean", requestId);
        }
        return node.booleanValue();
    }

    private double requireFiniteNumber(JsonNode root, String field, String operation, String requestId) {
        JsonNode node = root.get(field);
        if (node == null || !node.isNumber() || !Double.isFinite(node.doubleValue())) {
            throw malformed(operation, "'" + field + "' must be a finite number", requestId);
        }
        return node.doubleValue();
    }

    private long requireIntegralNumber(JsonNode root, String field, String operation, String requestId) {
        JsonNode node = root.get(field);
        if (node == null || !node.isNumber() || !node.canConvertToLong()) {
            throw malformed(operation, "'" + field + "' must be an integer", requestId);
        }
        return node.longValue();
    }

    private int requireFaceCount(JsonNode root, String operation, String requestId) {
        long value = requireIntegralNumber(root, "face_count", operation, requestId);
        if (value < 0) {
            throw malformed(operation, "'face_count' must be >= 0", requestId);
        }
        return (int) value;
    }

    private String textOrNull(JsonNode root, String field) {
        JsonNode node = root.get(field);
        return node != null && node.isTextual() ? node.textValue() : null;
    }

    private FaceServiceException malformed(String operation, String detail, String requestId) {
        log.warn("face service contract violation op={} detail={} requestId={}",
                operation, detail, requestId == null ? "<none>" : requestId);
        return new FaceServiceException(new FaceServiceError("MALFORMED_RESPONSE",
                "malformed " + operation + " response: " + detail, false, requestId, 200));
    }

    private static boolean isNotFound(FaceServiceException failure) {
        String code = failure.error().safeCode();
        return failure.error().httpStatus() == 404
                && ("SUBJECT_NOT_FOUND".equals(code) || "NAMESPACE_NOT_FOUND".equals(code));
    }

    private static MultipartBodyBuilder imageMultipart(byte[] image) {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("image", imagePart(image)).contentType(MediaType.APPLICATION_OCTET_STREAM);
        return builder;
    }

    private static MultipartBodyBuilder subjectMultipart(String subjectRef, byte[] image) {
        MultipartBodyBuilder builder = imageMultipart(image);
        builder.part("subject_id", subjectRef);
        // 显式 conflict：既有主体绝不被静默覆盖（与端口 SUBJECT_ALREADY_EXISTS 语义一致）。
        builder.part("on_exists", "conflict");
        return builder;
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

    private record VerifyOutcome(boolean matched, double similarity, double threshold, String requestId) {
    }
}
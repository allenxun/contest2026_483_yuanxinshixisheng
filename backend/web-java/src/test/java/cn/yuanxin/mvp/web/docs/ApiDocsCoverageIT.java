package cn.yuanxin.mvp.web.docs;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MvcResult;
import org.yaml.snakeyaml.Yaml;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/**
 * 联调文档<strong>覆盖率门禁</strong>：对<strong>实际生成</strong>的 {@code /v3/api-docs} 断言
 * 引擎施加后的完整性，并以权威契约 {@code backend/contracts/openapi/openapi.yaml} 的
 * {@code x-error-codes} 与成功响应码为期望集（不硬编码错误码清单）。
 *
 * <p><b>本测试在四条目录道补齐前预期失败</b>：它把所有问题累积后一次性报告，作为目录道的
 * 验收标尺与缺失清单。不得 {@code @Disabled}、不得弱化断言。</p>
 */
class ApiDocsCoverageIT extends AbstractWebIT {

    private static final List<String> METHODS = List.of("get", "post", "put", "delete", "patch");

    /**
     * 中文（CJK 统一表意文字）存在性判定。
     *
     * <p><b>必须用 {@code find()} 而非 {@code String.matches(".*[\\u4e00-\\u9fff].*")}</b>：
     * {@code matches()} 锚定整个输入，而 {@code .} 默认<strong>不匹配换行</strong>，
     * 因此任何<strong>多行</strong>中文文本（本项目的 description 用 Java 文本块书写，含 {@code \n}）
     * 都会被判为"无中文"。该缺陷曾使 34 个操作的 description 全部误报缺失，
     * 而单行的 summary 全部通过——症状恰为"只有 description 失败"。</p>
     */
    private static final Pattern CJK_PATTERN = Pattern.compile("[\\u4e00-\\u9fff]");

    /**
     * 经 orchestrator 审议核准的<strong>显式不透明</strong>自由结构字段（key = "Schema.property"）。
     * 只有这三项允许"零已知键 + 不透明声明"形态；文档中任何其它 {@code EXPLICIT_OPAQUE} 字段一律失败，
     * 防止"随便写一句 note"冒充权威不透明声明。
     *
     * <p>注意：{@code SkinReportListItem.reportSummary} <strong>不在</strong>清单内——Worker
     * （{@code assessment_analyze.py}）固定写入 {@code schema_version}/{@code conclusion}/
     * {@code headline_metrics} 三键，应在 freeFormDocs 中展开为 knownKeys 形态。</p>
     */
    private static final Set<String> APPROVED_OPAQUE_FIELDS = Set.of(
            "MicrocrystalObservationBody.state",
            "M4A04Metadata.reportedMicrocrystalState",
            "AppSessionRequestBody.installBindingMaterial");

    /** 生成 schema 名 → 契约 components schema 名（仅列已知不一致者；其余按同名对照）。 */
    private static final Map<String, String> CONTRACT_REQUEST_SCHEMA_ALIASES = Map.ofEntries(
            Map.entry("GimbalSessionRequestBody", "GimbalSessionRequest"),
            Map.entry("BindingBody", "GimbalBindingRequest"),
            Map.entry("EchoJobRequestBody", "SystemEchoJobRequest"),
            Map.entry("EchoJobAcceptedData", "SystemEchoJobAccepted"),
            Map.entry("EchoJobViewData", "SystemEchoJobView"),
            Map.entry("MicrocrystalObservationBody", "MicrocrystalObservationRequest"),
            Map.entry("HeartbeatBody", "GimbalHeartbeatRequest"),
            Map.entry("AppSessionRequestBody", "AppSessionRequest"),
            Map.entry("SessionRefreshRequestBody", "SessionRefreshRequest"),
            Map.entry("Request", "NotificationDestinationRequest"),
            Map.entry("SyncRequestDto", "ExecutionObservationSyncRequest"),
            Map.entry("ClosureRequestDto", "ExecutionClosureRequest"),
            Map.entry("A01Metadata", "M3A01Metadata"),
            Map.entry("A02Metadata", "M3A02Metadata"),
            Map.entry("CaptureDto", "Capture"),
            Map.entry("ExecutionObservationDto", "ExecutionObservation"),
            Map.entry("ExecutionRecordDto", "ExecutionRecord"));

    @Autowired
    private ApiDocsApplier apiDocsApplier;

    @Test
    @DisplayName("覆盖率门禁：34 操作文档完整、错误码/成功码与契约一致、参数与属性有描述、自由结构展开")
    void documentationCoverageGate() throws Exception {
        MvcResult r = mockMvc.perform(get("/v3/api-docs")).andReturn();
        assertTrue(r.getResponse().getStatus() == 200,
                "GET /v3/api-docs 必须 200："
                        + (r.getResponse().getStatus() == 200 ? "" : r.getResponse().getContentAsString()));
        JsonNode doc = JSON.readTree(r.getResponse().getContentAsString());

        Map<String, JsonNode> generated = generatedOperations(doc);
        Map<String, ContractOperation> contract = contractOperations();
        List<String> problems = new ArrayList<>();

        // 引擎报告：结构性错误必须为空；覆盖缺口逐条列出。
        if (apiDocsApplier.report().hasStructuralErrors()) {
            problems.add("引擎结构性错误: " + apiDocsApplier.report().structuralErrors());
        }
        for (String missing : apiDocsApplier.report().missingOperations) {
            problems.add("目录覆盖缺口（未文档化操作）: " + missing);
        }
        if (apiDocsApplier.report().undeclaredTags.size() > 0) {
            problems.add("目录使用了未声明 tag: " + apiDocsApplier.report().undeclaredTags);
        }

        // 1) 每操作：中文 summary/description、恰一个 tag。
        for (Map.Entry<String, JsonNode> e : generated.entrySet()) {
            JsonNode op = e.getValue();
            checkChinese(op, "summary", e.getKey(), problems);
            checkChinese(op, "description", e.getKey(), problems);
            JsonNode tags = op.path("tags");
            if (!(tags.isArray() && tags.size() == 1)) {
                problems.add(e.getKey() + " 必须恰有一个 tag，实际=" + tags);
            }
        }

        // 2) 错误响应 + x-error-codes 与契约一致。
        for (Map.Entry<String, JsonNode> e : generated.entrySet()) {
            JsonNode op = e.getValue();
            JsonNode responses = op.path("responses");
            boolean hasError = false;
            for (java.util.Iterator<String> it = responses.fieldNames(); it.hasNext(); ) {
                String code = it.next();
                if (code.length() == 3 && (code.charAt(0) == '4' || code.charAt(0) == '5')) {
                    hasError = true;
                }
            }
            if (!hasError) {
                problems.add(e.getKey() + " 未声明任何 4xx/5xx 响应");
            }
            Set<String> generatedCodes = generatedErrorCodes(op);
            ContractOperation expected = contract.get(e.getKey());
            if (expected != null) {
                if (!generatedCodes.equals(expected.errorCodes)) {
                    problems.add(e.getKey() + " x-error-codes 与契约不一致：generated="
                            + generatedCodes + " contract=" + expected.errorCodes);
                }
                for (String code : expected.errorCodes) {
                    String status = httpStatusOf(code);
                    if (status != null && !responses.has(status)) {
                        problems.add(e.getKey() + " 缺少错误码 " + code + " 对应 HTTP " + status + " 响应");
                    }
                }
            }

            // 3) 成功状态码与契约一致（契约操作）；并禁止“全是 200”。
            Set<String> generatedSuccess = successCodes(responses);
            if (expected != null && !generatedSuccess.equals(expected.successCodes)) {
                problems.add(e.getKey() + " 成功状态码与契约不一致：generated=" + generatedSuccess
                        + " contract=" + expected.successCodes);
            }
        }

        // 3b) 关键真实状态码显式核对（不得全是 200）。
        expectCode(generated, "POST /api/v1/member-access-grants", "201", problems);
        expectCode(generated, "POST /api/v1/member-access-grants", "200", problems);
        expectCode(generated, "POST /api/v1/skin-assessment-tasks", "202", problems);
        expectCode(generated, "PUT /api/v1/skin-assessment-tasks/{taskId}/photo-versions/{photoVersion}",
                "202", problems);
        expectCode(generated, "DELETE /api/v1/me/member-access-grants/{grantId}", "204", problems);
        expectCode(generated, "DELETE /api/v1/me/gimbal-bindings/{gimbalId}", "204", problems);
        expectCode(generated, "DELETE /api/v1/auth/sessions/current", "204", problems);
        // 204 必须无响应体
        for (String key : List.of("DELETE /api/v1/me/member-access-grants/{grantId}",
                "DELETE /api/v1/me/gimbal-bindings/{gimbalId}",
                "DELETE /api/v1/auth/sessions/current")) {
            JsonNode op = generated.get(normalizeKey(key));
            if (op != null && op.path("responses").has("204")
                    && op.path("responses").path("204").has("content")) {
                problems.add(key + " 的 204 不得携带 content");
            }
        }

        // 4) 所有参数有非空 description。
        for (Map.Entry<String, JsonNode> e : generated.entrySet()) {
            for (JsonNode p : e.getValue().path("parameters")) {
                String desc = p.path("description").asText("");
                if (desc.isBlank()) {
                    problems.add(e.getKey() + " 参数 " + p.path("in").asText() + ":"
                            + p.path("name").asText() + " 缺少 description");
                }
            }
        }

        // 5) 所有 schema 属性有非空 description；枚举/时间属性要点。
        JsonNode schemas = doc.path("components").path("schemas");
        schemas.fieldNames().forEachRemaining(name -> {
            JsonNode props = schemas.path(name).path("properties");
            props.fieldNames().forEachRemaining(prop -> {
                String desc = props.path(prop).path("description").asText("");
                if (desc.isBlank()) {
                    problems.add("schema " + name + "." + prop + " 缺少 description");
                }
            });
        });
        // 时间属性格式（抽样：以 At 结尾 / serverTime）
        schemas.fieldNames().forEachRemaining(name -> {
            JsonNode props = schemas.path(name).path("properties");
            props.fieldNames().forEachRemaining(prop -> {
                if (prop.endsWith("At") || "serverTime".equals(prop)) {
                    JsonNode p = props.path(prop);
                    String fmt = p.path("format").asText("");
                    String desc = p.path("description").asText("");
                    if (!"date-time".equals(fmt) && !desc.contains("RFC3339")) {
                        problems.add("schema " + name + "." + prop + " 时间属性须 format=date-time 或描述含 RFC3339");
                    }
                }
            });
        });

        // 6) 自由结构<strong>动态扫描</strong>：遍历全部 components.schemas[*].properties[*]，
        //    凡"无结构对象"（type=object 且无 properties 且无 additionalProperties；或 $ref 指向
        //    空壳 schema 如 JsonNode）都必须 EXPANDED 或 EXPLICIT_OPAQUE；不透明声明还须在核准清单内。
        Set<String> opaqueFound = new LinkedHashSet<>();
        for (java.util.Iterator<String> sit = schemas.fieldNames(); sit.hasNext(); ) {
            String schemaName = sit.next();
            JsonNode props = schemas.path(schemaName).path("properties");
            for (java.util.Iterator<String> pit = props.fieldNames(); pit.hasNext(); ) {
                String propName = pit.next();
                JsonNode prop = props.path(propName);
                String fq = schemaName + "." + propName;
                ApiDocsApplier.FreeFormGate gate = ApiDocsApplier.classifyFreeForm(prop);
                if (gate == ApiDocsApplier.FreeFormGate.EXPLICIT_OPAQUE) {
                    opaqueFound.add(fq);
                    if (!APPROVED_OPAQUE_FIELDS.contains(fq)) {
                        problems.add("未经核准的不透明声明: " + fq
                                + " —— 请补充经取证的 knownKeys，或由 orchestrator 审议后加入核准清单");
                    }
                    continue;
                }
                if (ApiDocsApplier.isUnstructuredObject(prop, schemas)) {
                    switch (gate) {
                        case OPAQUE_MISSING_ADDITIONAL_PROPERTIES -> problems.add(
                                "自由结构有不透明声明但未显式设置 additionalProperties: "
                                        + fq + " = " + prop);
                        case NOT_DECLARED -> problems.add(
                                "自由结构未展开且无不透明声明（既无 properties 也无显式不透明说明）: "
                                        + fq + " = " + prop);
                        default -> {
                            // 候选按定义不含 properties，不会走到 EXPANDED/EXPLICIT_OPAQUE
                        }
                    }
                }
            }
        }
        for (String approved : APPROVED_OPAQUE_FIELDS) {
            if (!opaqueFound.contains(approved)) {
                problems.add("核准清单字段在文档中并非显式不透明形态（清单可能陈旧）: " + approved);
            }
        }

        // 6b) 契约 required 交叉校验：multipart part 必填性 + 请求体 schema required 集。
        crossCheckContractRequired(generated, schemas, problems);

        // 7) 至少 5 个关键 schema 带脱敏 example（component 属性级或 schema 级）。
        int withExample = 0;
        for (java.util.Iterator<String> it = schemas.fieldNames(); it.hasNext(); ) {
            JsonNode schema = schemas.path(it.next());
            if (schema.hasNonNull("example")) {
                withExample++;
                continue;
            }
            JsonNode props = schema.path("properties");
            for (java.util.Iterator<String> pit = props.fieldNames(); pit.hasNext(); ) {
                if (props.path(pit.next()).hasNonNull("example")) {
                    withExample++;
                    break;
                }
            }
        }
        if (withExample < 5) {
            problems.add("带 example 的 schema 不足：需要 ≥5，实际=" + withExample);
        }

        // 8) 不回归：bearerAuth、全局 security、4 公开端点 security=[]、契约业务路由齐全。
        JsonNode scheme = doc.path("components").path("securitySchemes").path("bearerAuth");
        if (!"http".equals(scheme.path("type").asText())
                || !"bearer".equals(scheme.path("scheme").asText())) {
            problems.add("bearerAuth 安全方案回归");
        }
        if (doc.path("security").size() != 1) {
            problems.add("全局 security 回归（应为 bearerAuth）");
        }
        Map<String, String> publicOps = Map.of(
                "/api/v1/auth/sms-challenges", "post",
                "/api/v1/auth/sessions", "post",
                "/api/v1/auth/session-refreshes", "post",
                "/api/v1/gimbal-sessions", "post");
        for (Map.Entry<String, String> e : publicOps.entrySet()) {
            JsonNode op = doc.path("paths").path(e.getKey()).path(e.getValue());
            if (!(op.path("security").isArray() && op.path("security").size() == 0)) {
                problems.add("公开端点 security 回归: " + e);
            }
        }
        Set<String> missingContractRoutes = new LinkedHashSet<>(contract.keySet());
        missingContractRoutes.removeAll(generated.keySet());
        if (!missingContractRoutes.isEmpty()) {
            problems.add("契约业务路由未出现在生成文档: " + missingContractRoutes);
        }

        assertTrue(problems.isEmpty(),
                "联调文档覆盖率门禁未通过（" + problems.size() + " 项）：\n  - "
                        + String.join("\n  - ", problems));
    }

    // ------------------------------------------------------------------ helpers

    private static void checkChinese(JsonNode op, String field, String key, List<String> problems) {
        String value = op.path(field).asText("");
        if (value.isBlank()) {
            problems.add(key + " 缺少 " + field);
        } else if (!CJK_PATTERN.matcher(value).find()) {
            problems.add(key + " 的 " + field + " 缺少中文说明");
        }
    }

    private static void expectCode(Map<String, JsonNode> generated, String key, String code,
                                   List<String> problems) {
        JsonNode op = generated.get(normalizeKey(key));
        if (op == null) {
            problems.add("操作缺失: " + key);
            return;
        }
        if (!op.path("responses").has(code)) {
            Set<String> actual = new LinkedHashSet<>();
            op.path("responses").fieldNames().forEachRemaining(actual::add);
            problems.add(key + " 缺少真实成功状态码 " + code + "（实际=" + actual + "）");
        }
    }

    private static String normalizeKey(String key) {
        return key.replaceAll("\\{[^/]*\\}", "{}");
    }

    // ---------------- 6b) 契约 required 交叉校验 ----------------

    /**
     * （a）multipart part required 与契约操作 {@code requestBody.content.multipart/form-data.schema.required}
     * 精确比对；（b）生成文档中全部请求体相关 schema 的 {@code required} 与契约 components 比对
     * （生成名经 {@link #CONTRACT_REQUEST_SCHEMA_ALIASES} 映射）。
     * 少于契约 → 失败（应经 {@code requiredProperties()} 修正）；多于契约 → 失败（不得 invent）。
     * 无契约对应者<strong>跳过并在输出中披露计数</strong>，不静默。
     */
    private static void crossCheckContractRequired(Map<String, JsonNode> generated, JsonNode schemas,
                                                   List<String> problems) throws Exception {
        Map<String, Set<String>> contractMultipart = contractMultipartRequired();
        Map<String, Set<String>> contractSchemas = contractComponentRequired();

        // (a) multipart part required 精确比对。
        List<String> skippedMultipart = new ArrayList<>();
        for (Map.Entry<String, JsonNode> e : generated.entrySet()) {
            JsonNode multipart = e.getValue().path("requestBody")
                    .path("content").path("multipart/form-data").path("schema");
            if (multipart.isMissingNode()) {
                continue;
            }
            Set<String> expected = contractMultipart.get(e.getKey());
            if (expected == null) {
                skippedMultipart.add(e.getKey());
                continue;
            }
            Set<String> actual = stringSet(multipart.path("required"));
            if (!actual.equals(expected)) {
                problems.add("multipart part required 与契约不一致: " + e.getKey()
                        + " generated=" + actual + " contract=" + expected
                        + "（条件必填 part 用 MultipartPartDoc.binary(..., required=false)）");
            }
        }

        // (b) 请求体 schema required 集比对（JSON 顶层 + multipart JSON part + 递归嵌套）。
        List<String> skippedSchemas = new ArrayList<>();
        for (String generatedName : requestSchemaNames(generated, schemas)) {
            String contractName = CONTRACT_REQUEST_SCHEMA_ALIASES.getOrDefault(generatedName, generatedName);
            if (!contractSchemas.containsKey(contractName)) {
                skippedSchemas.add(generatedName + "→" + contractName);
                continue;
            }
            Set<String> actual = stringSet(schemas.path(generatedName).path("required"));
            Set<String> expected = contractSchemas.get(contractName);
            if (actual.equals(expected)) {
                continue;
            }
            Set<String> missing = new LinkedHashSet<>(expected);
            missing.removeAll(actual);
            Set<String> extra = new LinkedHashSet<>(actual);
            extra.removeAll(expected);
            if (!extra.isEmpty()) {
                problems.add("请求体 schema required 多于契约（不得 invent 必填性）: "
                        + generatedName + "→" + contractName + " extra=" + extra
                        + " generated=" + actual + " contract=" + expected);
            } else {
                problems.add("请求体 schema required 少于契约（应经 requiredProperties() 修正）: "
                        + generatedName + "→" + contractName + " missing=" + missing
                        + " generated=" + actual + " contract=" + expected);
            }
        }

        if (!skippedMultipart.isEmpty() || !skippedSchemas.isEmpty()) {
            System.out.println("[coverage-gate] 无契约可比对、已跳过并披露的请求体:"
                    + " multipartOps=" + skippedMultipart + " requestSchemas=" + skippedSchemas);
        }
    }

    private static Set<String> stringSet(JsonNode arrayNode) {
        Set<String> out = new LinkedHashSet<>();
        if (arrayNode != null && arrayNode.isArray()) {
            arrayNode.forEach(n -> out.add(n.asText()));
        }
        return out;
    }

    /** 生成文档中全部请求体相关 schema 名（走 requestBody 树 + 递归进入 components 的嵌套 $ref）。 */
    private static Set<String> requestSchemaNames(Map<String, JsonNode> generated, JsonNode schemas) {
        Set<String> out = new LinkedHashSet<>();
        java.util.Deque<String> queue = new java.util.ArrayDeque<>();
        for (JsonNode op : generated.values()) {
            collectSchemaRefs(op.path("requestBody"), out, queue);
        }
        while (!queue.isEmpty()) {
            String name = queue.poll();
            JsonNode schema = schemas.path(name);
            if (schema.isMissingNode()) {
                continue;
            }
            collectSchemaRefs(schema, out, queue);
        }
        return out;
    }

    private static void collectSchemaRefs(JsonNode node, Set<String> out, java.util.Deque<String> queue) {
        if (node == null || node.isMissingNode() || node.isNull()) {
            return;
        }
        if (node.isObject()) {
            JsonNode ref = node.get("$ref");
            if (ref != null && ref.isTextual()) {
                String v = ref.asText();
                String name = v.substring(v.lastIndexOf('/') + 1);
                if (out.add(name)) {
                    queue.add(name);
                }
            }
            node.fields().forEachRemaining(e -> collectSchemaRefs(e.getValue(), out, queue));
        } else if (node.isArray()) {
            node.forEach(child -> collectSchemaRefs(child, out, queue));
        }
    }

    /** 契约全部 multipart 操作的 part required（key = "METHOD {}"）。 */
    @SuppressWarnings("unchecked")
    private static Map<String, Set<String>> contractMultipartRequired() throws Exception {
        Map<String, Object> contract = loadContract();
        Map<String, Object> paths = (Map<String, Object>) contract.get("paths");
        Map<String, Set<String>> out = new LinkedHashMap<>();
        if (paths == null) {
            return out;
        }
        for (Map.Entry<String, Object> e : paths.entrySet()) {
            Map<String, Object> item = (Map<String, Object>) e.getValue();
            for (String m : METHODS) {
                Object raw = item.get(m);
                if (!(raw instanceof Map<?, ?> opMap)) {
                    continue;
                }
                Object rb = opMap.get("requestBody");
                if (!(rb instanceof Map<?, ?> rbMap)) {
                    continue;
                }
                Object content = rbMap.get("content");
                if (!(content instanceof Map<?, ?> contentMap)) {
                    continue;
                }
                Object mp = contentMap.get("multipart/form-data");
                if (!(mp instanceof Map<?, ?> mpMap)) {
                    continue;
                }
                Object schema = mpMap.get("schema");
                if (!(schema instanceof Map<?, ?> schemaMap)) {
                    continue;
                }
                Set<String> required = new LinkedHashSet<>();
                Object req = schemaMap.get("required");
                if (req instanceof List<?> list) {
                    list.forEach(r -> required.add(String.valueOf(r)));
                }
                out.put(m.toUpperCase() + " " + normalize(e.getKey()), required);
            }
        }
        return out;
    }

    /** 契约 components.schemas 中对象 schema 的 required 集（无 required 者视为空集）。 */
    @SuppressWarnings("unchecked")
    private static Map<String, Set<String>> contractComponentRequired() throws Exception {
        Map<String, Object> contract = loadContract();
        Object compsRaw = contract.get("components");
        if (!(compsRaw instanceof Map<?, ?> comps)) {
            return Map.of();
        }
        Object schemasRaw = comps.get("schemas");
        if (!(schemasRaw instanceof Map<?, ?> schemas)) {
            return Map.of();
        }
        Map<String, Set<String>> out = new LinkedHashMap<>();
        for (Map.Entry<?, ?> e : schemas.entrySet()) {
            if (!(e.getValue() instanceof Map<?, ?> s) || !(s.get("properties") instanceof Map<?, ?>)) {
                continue; // 只对照对象 schema
            }
            Set<String> required = new LinkedHashSet<>();
            Object req = s.get("required");
            if (req instanceof List<?> list) {
                list.forEach(r -> required.add(String.valueOf(r)));
            }
            out.put(String.valueOf(e.getKey()), required);
        }
        return out;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> loadContract() throws Exception {
        Path yamlPath = Path.of("..", "contracts", "openapi", "openapi.yaml");
        assertTrue(Files.exists(yamlPath), "contract not found at " + yamlPath.toAbsolutePath());
        try (InputStream in = Files.newInputStream(yamlPath)) {
            return new Yaml().load(in);
        }
    }

    private static Set<String> generatedErrorCodes(JsonNode op) {
        Set<String> out = new LinkedHashSet<>();
        JsonNode ext = op.path("x-error-codes");
        if (ext.isArray()) {
            ext.forEach(n -> out.add(n.asText()));
        }
        return out;
    }

    private static Set<String> successCodes(JsonNode responses) {
        Set<String> out = new LinkedHashSet<>();
        responses.fieldNames().forEachRemaining(code -> {
            if (code.length() == 3 && code.charAt(0) == '2') {
                out.add(code);
            }
        });
        return out;
    }

    private static String httpStatusOf(String errorCode) {
        try {
            return String.valueOf(cn.yuanxin.mvp.web.error.ErrorCode.valueOf(errorCode)
                    .defaultStatus().value());
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    /** 生成文档的对外操作：key = "METHOD {}"（路径变量归一化）；只统计 /api/**。 */
    private static Map<String, JsonNode> generatedOperations(JsonNode doc) {
        Map<String, JsonNode> out = new LinkedHashMap<>();
        JsonNode paths = doc.path("paths");
        paths.fieldNames().forEachRemaining(p -> {
            if (!p.startsWith("/api/")) {
                return; // 测试基础设施端点（/internal-test/**）不属联调文档面
            }
            JsonNode item = paths.get(p);
            for (String m : METHODS) {
                if (item.has(m)) {
                    out.put(m.toUpperCase() + " " + normalize(p), item.get(m));
                }
            }
        });
        return out;
    }

    private record ContractOperation(Set<String> errorCodes, Set<String> successCodes) {
    }

    /** 契约操作：key = "METHOD {}"；只取带 x-api-id 的业务操作。 */
    @SuppressWarnings("unchecked")
    private static Map<String, ContractOperation> contractOperations() throws Exception {
        Path yamlPath = Path.of("..", "contracts", "openapi", "openapi.yaml");
        assertTrue(Files.exists(yamlPath), "contract not found at " + yamlPath.toAbsolutePath());
        Map<String, Object> contract;
        try (InputStream in = Files.newInputStream(yamlPath)) {
            contract = new Yaml().load(in);
        }
        Map<String, Object> paths = (Map<String, Object>) contract.get("paths");
        assertNotNull(paths, "contract has no paths section");
        Map<String, ContractOperation> out = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : paths.entrySet()) {
            Map<String, Object> item = (Map<String, Object>) e.getValue();
            for (String m : METHODS) {
                Object raw = item.get(m);
                if (!(raw instanceof Map<?, ?> opMap) || !opMap.containsKey("x-api-id")) {
                    continue;
                }
                Set<String> errorCodes = new LinkedHashSet<>();
                Object xec = opMap.get("x-error-codes");
                if (xec instanceof List<?> list) {
                    list.forEach(c -> errorCodes.add(String.valueOf(c)));
                }
                Set<String> successCodes = new LinkedHashSet<>();
                Object responses = opMap.get("responses");
                if (responses instanceof Map<?, ?> respMap) {
                    for (Object code : respMap.keySet()) {
                        String c = String.valueOf(code);
                        if (c.length() == 3 && c.charAt(0) == '2') {
                            successCodes.add(c);
                        }
                    }
                }
                out.put(m.toUpperCase() + " " + normalize(e.getKey()),
                        new ContractOperation(errorCodes, successCodes));
            }
        }
        return out;
    }

    private static String normalize(String path) {
        return path.replaceAll("\\{[^/]*\\}", "{}");
    }
}

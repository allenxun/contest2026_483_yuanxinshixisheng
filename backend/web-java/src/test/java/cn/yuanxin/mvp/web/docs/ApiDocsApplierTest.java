package cn.yuanxin.mvp.web.docs;

import cn.yuanxin.mvp.web.docs.catalog.ApiDocEntry;
import cn.yuanxin.mvp.web.docs.catalog.ApiDocsCatalog;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.Paths;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.IntegerSchema;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.parameters.RequestBody;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import io.swagger.v3.oas.models.tags.Tag;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 文档施加引擎的<strong>纯单元</strong>自证（不起 Spring 上下文）：
 * 用合成的 OpenAPI（模拟基线形态：{@code data} 无结构、响应只有 200 OK、错误请求体为
 * {@code PrincipalContext}、存在自由结构字段）+ 合成目录，断言施加结果，并用负向用例证明
 * 校验有判别力（未知键 / 重复键 / 参数不符 → fail fast；覆盖缺口 → 报告但不抛）。
 */
class ApiDocsApplierTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String REQUEST_ID_REF = "#/components/schemas/ErrorEnvelope";

    // ---- synthetic payload types (registered by the engine via ModelConverters) ----
    public record SyntheticResult(String id, Integer value) {
    }

    public record SyntheticMetadata(String captureId, String consentEvidenceRef) {
    }

    public record SyntheticBody(String name, Integer count, Object state, List<Object> tags) {
    }

    public record SyntheticItem(String id, String name) {
    }

    // ------------------------------------------------------------------ main positive path

    @Test
    @DisplayName("正向：tag/summary/description、参数、multipart 重建、真实状态码、typed data、错误合并、属性/自由结构")
    void appliesAllDocumentationFacets() {
        OpenAPI openApi = syntheticDoc();
        ApiDocsApplier applier = new ApiDocsApplier(List.of(validCatalog()), MAPPER);
        applier.customise(openApi);

        // 操作级文档
        Operation post = op(openApi, "/api/v1/synthetic/items", PathItem.HttpMethod.POST);
        assertEquals("Synthetic", post.getTags().get(0));
        assertEquals("创建合成项", post.getSummary());
        assertTrue(post.getDescription().contains("多行说明"));

        // 参数：requiredOverride + example
        Parameter idem = post.getParameters().stream()
                .filter(p -> "Idempotency-Key".equals(p.getName())).findFirst().orElseThrow();
        assertTrue(idem.getRequired(), "requiredOverride=true 应覆盖生成文档的 false");
        assertEquals("key-1", idem.getExample());
        assertTrue(idem.getDescription().contains("1-128"));

        // multipart 请求体重建（修掉 PrincipalContext 被当成请求体的错误）
        RequestBody rb = post.getRequestBody();
        assertNotNull(rb);
        MediaType multipart = rb.getContent().get("multipart/form-data");
        assertNotNull(multipart, "请求体应为 multipart/form-data");
        Schema<?> mpSchema = multipart.getSchema();
        assertEquals(Boolean.FALSE, mpSchema.getAdditionalProperties());
        Schema<?> metadata = (Schema<?>) mpSchema.getProperties().get("metadata");
        assertTrue(metadata.get$ref().contains("SyntheticMetadata"), "JSON part 应 $ref 可展开结构");
        assertNotNull(openApi.getComponents().getSchemas().get("SyntheticMetadata"));
        Schema<?> face = (Schema<?>) mpSchema.getProperties().get("face");
        assertEquals("string", face.getType());
        assertEquals("binary", face.getFormat());
        assertEquals("application/json", multipart.getEncoding().get("metadata").getContentType());
        assertFalse(post.getRequestBody().getContent().containsKey("application/json"));

        // 成功响应：真实码 201/200，data 为 $ref 具体类型，占位 200 OK 被替换
        ApiResponses responses = post.getResponses();
        assertNotNull(responses.get("201"));
        assertNotNull(responses.get("200"));
        assertNotNull(responses.get("200").getContent(),
                "200 应为幂等重放的 typed 响应，而非占位 {\"description\":\"OK\"}");
        Schema<?> env = responses.get("201").getContent().get("application/json").getSchema();
        assertEquals("#/components/schemas/SyntheticResult",
                ((Schema<?>) env.getProperties().get("data")).get$ref());
        assertNotNull(openApi.getComponents().getSchemas().get("SyntheticResult"));
        assertNotNull(openApi.getComponents().getSchemas().get("Meta"));
        assertTrue(((Schema<?>) env.getProperties().get("requestId")).getDescription().contains("X-Request-Id"));
        assertTrue(((Schema<?>) env.getProperties().get("meta")).getDescription().contains("RFC3339"));

        // 错误响应：同状态多码合并（400/409/501），409 含两个码；ErrorEnvelope 注册
        assertNotNull(responses.get("400"));
        assertNotNull(responses.get("501"));
        ApiResponse conflict = responses.get("409");
        assertNotNull(conflict, "409 必须由错误码生成（REQUEST_IN_PROGRESS + IDEMPOTENCY_CONTENT_CONFLICT）");
        assertTrue(conflict.getDescription().contains("REQUEST_IN_PROGRESS"));
        assertTrue(conflict.getDescription().contains("IDEMPOTENCY_CONTENT_CONFLICT"));
        assertNotNull(openApi.getComponents().getSchemas().get("ErrorEnvelope"));
        assertEquals(List.of("INVALID_INPUT", "REQUEST_IN_PROGRESS",
                        "IDEMPOTENCY_CONTENT_CONFLICT", "NOT_IMPLEMENTED"),
                post.getExtensions().get("x-error-codes"));

        // 204 无 content
        Operation delete = op(openApi, "/api/v1/synthetic/items/{itemId}", PathItem.HttpMethod.DELETE);
        assertNotNull(delete.getResponses().get("204"));
        assertNull(delete.getResponses().get("204").getContent(), "204 不得有响应体");
        assertNull(delete.getResponses().get("200"), "204 端点的占位 200 必须移除");

        // JSON 请求体 class 覆盖（GET 之外的合成：这里用 DELETE 之外的 POST 已覆盖 multipart；单独验证 JSON 覆盖见下一个用例）
        // 属性级文档（含新注册类型）
        Schema<?> result = openApi.getComponents().getSchemas().get("SyntheticResult");
        assertEquals("结果 ID", ((Schema<?>) result.getProperties().get("id")).getDescription());
        Schema<?> value = (Schema<?>) result.getProperties().get("value");
        assertTrue(value.getDescription().contains("单位：次"));
        assertEquals(3, value.getExample());

        Schema<?> meta = openApi.getComponents().getSchemas().get("Meta");
        assertTrue(((Schema<?>) meta.getProperties().get("replayed")).getDescription().contains("重放"));
        assertEquals("date-time", ((Schema<?>) meta.getProperties().get("serverTime")).getFormat());

        // 自由结构展开（object → 显式结构，extensible=true）
        Schema<?> body = openApi.getComponents().getSchemas().get("SyntheticBody");
        Schema<?> state = (Schema<?>) body.getProperties().get("state");
        assertEquals("object", state.getType());
        assertEquals(Boolean.TRUE, state.getAdditionalProperties());
        assertNotNull(state.getProperties().get("power"));
        assertEquals("boolean", ((Schema<?>) state.getProperties().get("power")).getType());
        assertTrue(state.getDescription().contains("可扩展边界"));

        // 覆盖率：三个操作均被覆盖 → 无缺失
        assertTrue(applier.report().missingOperations.isEmpty(),
                "全部覆盖时不得报告缺失: " + applier.report().missingOperations);
        assertFalse(applier.report().hasStructuralErrors(), applier.report().structuralErrors().toString());
    }

    @Test
    @DisplayName("正向：requestBodyClass 覆盖自动推导的 JSON 请求体")
    void requestBodyClassOverridesJsonBody() {
        OpenAPI openApi = syntheticDoc();
        // 给 GET 加一个错误的 JSON 请求体，再用 requestBodyClass 覆盖（模拟 PrincipalContext 式错误）。
        Operation get = op(openApi, "/api/v1/synthetic/items/{itemId}", PathItem.HttpMethod.GET);
        get.setRequestBody(new RequestBody().content(new Content().addMediaType("application/json",
                new MediaType().schema(new Schema<>().$ref("#/components/schemas/PrincipalContext")))));

        Map<String, ApiDocEntry> entries = new LinkedHashMap<>(validCatalog().entries());
        entries.put("GET /api/v1/synthetic/items/{itemId}", new ApiDocEntry(
                "Synthetic", "查询合成项", "覆盖请求体", List.of(
                        ParamDoc("itemId", "path", "项 ID", null, null),
                        ParamDoc("limit", "query", "分页大小，默认 20 上限 100", "20", null)),
                List.of(), SyntheticBody.class, "真实请求体为 SyntheticBody",
                List.of(ApiDocEntry.SuccessDoc.json("200", "查询成功", SyntheticResult.class)),
                List.of(ErrorCode.RESOURCE_NOT_VISIBLE)));

        new ApiDocsApplier(List.of(new TestCatalog(entries, Map.of(), Map.of(),
                List.of(new Tag().name("Synthetic")))), MAPPER).customise(openApi);

        Operation getAfter = op(openApi, "/api/v1/synthetic/items/{itemId}", PathItem.HttpMethod.GET);
        assertEquals("#/components/schemas/SyntheticBody", getAfter.getRequestBody().getContent()
                .get("application/json").getSchema().get$ref());
        assertNotNull(openApi.getComponents().getSchemas().get("SyntheticBody"));
        assertEquals("真实请求体为 SyntheticBody", getAfter.getRequestBody().getDescription());
    }

    // ------------------------------------------------------------------ free-form array

    @Test
    @DisplayName("正向：自由结构为数组时表达为 array of <结构>，additionalProperties 反映封闭边界")
    void freeFormArrayExpandsToArrayOfStructure() {
        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocsCatalog.FreeFormDoc> free = Map.of(
                "SyntheticBody.tags", new ApiDocsCatalog.FreeFormDoc(
                        "事件列表", Map.of("code", "string: 事件码", "at", "string: 时间 RFC3339"),
                        false, "封闭白名单，服务端只认 code/at", "[{\"code\":\"x\",\"at\":\"2026-09-13T08:30:00Z\"}]"));
        Map<String, ApiDocEntry> entries = new LinkedHashMap<>(validCatalog().entries());
        entries.put("GET /api/v1/synthetic/items/{itemId}", new ApiDocEntry(
                "Synthetic", "查询合成项", "数组自由结构", List.of(
                        ParamDoc("itemId", "path", "项 ID", null, null),
                        ParamDoc("limit", "query", "分页大小", "20", null)),
                List.of(), null, null,
                List.of(ApiDocEntry.SuccessDoc.json("200", "查询成功", SyntheticBody.class)),
                List.of(ErrorCode.RESOURCE_NOT_VISIBLE)));
        new ApiDocsApplier(List.of(new TestCatalog(entries, Map.of(), free,
                List.of(new Tag().name("Synthetic")))), MAPPER).customise(openApi);

        Schema<?> body = openApi.getComponents().getSchemas().get("SyntheticBody");
        Schema<?> tags = (Schema<?>) body.getProperties().get("tags");
        assertEquals("array", tags.getType());
        Schema<?> items = tags.getItems();
        assertEquals("object", items.getType());
        assertEquals(Boolean.FALSE, items.getAdditionalProperties());
        assertNotNull(items.getProperties().get("code"));
        assertNotNull(items.getProperties().get("at"));
    }

    // ------------------------------------------------------------------ opaque free-form + gate rule

    @Test
    @DisplayName("不透明声明：空 knownKeys + 非空 extensibilityNote → 显式不透明对象（含 additionalProperties/描述）；空 note → 未声明")
    void opaqueFreeFormDeclaration() {
        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocsCatalog.FreeFormDoc> free = Map.of(
                "SyntheticBody.state", new ApiDocsCatalog.FreeFormDoc(
                        "来自目录的说明：服务端当前不消费该字段（原样接受）。",
                        Map.of(), true,
                        "结构未冻结：已知键集合为空，客户端不得依赖任何具体键"
                                + "（依据 契约 x-detail: skeleton）。",
                        null),
                "SyntheticBody.tags", new ApiDocsCatalog.FreeFormDoc(
                        "普通数组描述（无任何不透明/未冻结表述）。",
                        Map.of(), true, null, null));
        new ApiDocsApplier(List.of(new TestCatalog(validCatalog().entries(), Map.of(), free,
                List.of(new Tag().name("Synthetic")))), MAPPER).customise(openApi);

        Schema<?> body = openApi.getComponents().getSchemas().get("SyntheticBody");
        Schema<?> state = (Schema<?>) body.getProperties().get("state");
        assertTrue(state.getProperties() == null || state.getProperties().isEmpty(),
                "不透明对象不生成任何已知键 property");
        assertEquals(Boolean.TRUE, state.getAdditionalProperties(), "additionalProperties 必须显式设置");
        assertTrue(state.getDescription().contains("不透明"));
        assertTrue(state.getDescription().contains("未冻结"));
        assertTrue(state.getDescription().contains("服务端当前不消费"), "须保留目录提供的消费语义");
        assertEquals(ApiDocsApplier.FreeFormGate.EXPLICIT_OPAQUE,
                ApiDocsApplier.classifyFreeForm(MAPPER.valueToTree(state)));

        Schema<?> tags = (Schema<?>) body.getProperties().get("tags");
        assertEquals(ApiDocsApplier.FreeFormGate.NOT_DECLARED,
                ApiDocsApplier.classifyFreeForm(MAPPER.valueToTree(tags)),
                "空 knownKeys 且无 extensibilityNote 不构成不透明声明，仍判未声明");
    }

    @Test
    @DisplayName("门禁判定四态：展开 / 显式不透明 / 有声明缺 additionalProperties / 裸 object（负向证明有判别力）")
    void freeFormGateClassification() throws Exception {
        assertEquals(ApiDocsApplier.FreeFormGate.EXPANDED,
                ApiDocsApplier.classifyFreeForm(MAPPER.readTree(
                        "{\"type\":\"object\",\"properties\":{\"a\":{\"type\":\"string\"}}}")));
        assertEquals(ApiDocsApplier.FreeFormGate.EXPANDED,
                ApiDocsApplier.classifyFreeForm(MAPPER.readTree(
                        "{\"type\":\"array\",\"items\":{\"type\":\"object\",\"properties\":{\"a\":{}}}}")));
        // 夹具使用引擎实际产出的形态：显式不透明声明必带规范标记 OPAQUE_MARKER。
        assertEquals(ApiDocsApplier.FreeFormGate.EXPLICIT_OPAQUE,
                ApiDocsApplier.classifyFreeForm(MAPPER.readTree(
                        "{\"type\":\"object\",\"additionalProperties\":true,"
                                + "\"description\":\"" + ApiDocsApplier.OPAQUE_MARKER
                                + "本字段为开放结构、未冻结，已知键集合为空\"}")));
        assertEquals(ApiDocsApplier.FreeFormGate.OPAQUE_MISSING_ADDITIONAL_PROPERTIES,
                ApiDocsApplier.classifyFreeForm(MAPPER.readTree(
                        "{\"type\":\"object\","
                                + "\"description\":\"" + ApiDocsApplier.OPAQUE_MARKER
                                + "本字段为开放结构、未冻结，客户端不得依赖任何具体键名\"}")));
        // 负向（收紧后的关键回归）：描述里只是"提到"不透明/未冻结字样、但没有规范标记，
        // 不构成声明——证明判定不再退化为自由文本关键词匹配。
        assertEquals(ApiDocsApplier.FreeFormGate.NOT_DECLARED,
                ApiDocsApplier.classifyFreeForm(MAPPER.readTree(
                        "{\"type\":\"object\",\"additionalProperties\":true,"
                                + "\"description\":\"普通数组描述（无任何不透明/未冻结表述）。\"}")),
                "仅含关键词而无规范标记不得判为显式不透明");
        assertEquals(ApiDocsApplier.FreeFormGate.NOT_DECLARED,
                ApiDocsApplier.classifyFreeForm(MAPPER.readTree("{\"type\":\"object\"}")),
                "裸 {type:object} 无声明仍必须失败");
        assertEquals(ApiDocsApplier.FreeFormGate.NOT_DECLARED,
                ApiDocsApplier.classifyFreeForm(MAPPER.readTree(
                        "{\"type\":\"object\",\"additionalProperties\":true}")),
                "仅 additionalProperties 而无不透明声明仍必须失败");
    }

    // ------------------------------------------------------------------ list responses

    @Test
    @DisplayName("正向：列表 jsonList 展开 data.items 为 $ref 条目类型、nextCursor nullable string、条目 propertyDocs 生效、修剪不误删")
    void listResponseExpandsItemType() {
        OpenAPI openApi = syntheticListDoc();
        Map<String, ApiDocEntry> entries = new LinkedHashMap<>();
        entries.put("GET /api/v1/synthetic/list", new ApiDocEntry(
                "Synthetic", "列出合成项", "列表分页语义",
                List.of(ParamDoc("limit", "query", "分页大小，默认 20、上限 100", "20", null),
                        ParamDoc("cursor", "query", "keyset 游标，原样回传", null, null)),
                List.of(), null, null,
                List.of(ApiDocEntry.SuccessDoc.jsonList("200", "列表成功", SyntheticItem.class)),
                List.of(ErrorCode.RESOURCE_NOT_VISIBLE)));
        Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> props = Map.of(
                "SyntheticItem", Map.of(
                        "id", ApiDocsCatalog.PropertyDoc.of("条目 ID", "i-1"),
                        "name", ApiDocsCatalog.PropertyDoc.of("名称", "样本")));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(entries, props,
                Map.of(), List.of(new Tag().name("Synthetic")))), MAPPER);
        applier.customise(openApi);

        Operation op = op(openApi, "/api/v1/synthetic/list", PathItem.HttpMethod.GET);
        Schema<?> env = op.getResponses().get("200").getContent().get("application/json").getSchema();
        // data 为内联 ListData 形状
        Schema<?> data = (Schema<?>) env.getProperties().get("data");
        assertEquals("object", data.getType());
        assertEquals(List.of("items"), data.getRequired(), "items 必填；nextCursor 可 null 但保留");
        Schema<?> items = (Schema<?>) data.getProperties().get("items");
        assertEquals("array", items.getType());
        assertEquals("#/components/schemas/SyntheticItem", items.getItems().get$ref());
        assertTrue(items.getDescription().contains("默认 20"), "items 描述须含分页语义");
        assertTrue(items.getDescription().contains("上限 100"));
        Schema<?> next = (Schema<?>) data.getProperties().get("nextCursor");
        assertEquals("string", next.getType());
        assertEquals(Boolean.TRUE, next.getNullable(), "nextCursor 必须 nullable string");
        assertTrue(next.getDescription().contains("null"), "nextCursor 描述须说明 null 语义");

        // 条目类型已注册，且其 propertyDocs 生效（修剪未误删：$ref 在内联 items 内）
        Schema<?> item = openApi.getComponents().getSchemas().get("SyntheticItem");
        assertNotNull(item, "条目类型必须注册进 components 且不被修剪");
        assertEquals("条目 ID", ((Schema<?>) item.getProperties().get("id")).getDescription());
        assertEquals("名称", ((Schema<?>) item.getProperties().get("name")).getDescription());
        assertFalse(openApi.getComponents().getSchemas().containsKey("ListData"),
                "不可达的 ListData 组件应被修剪（与 PrincipalContext/空壳 JsonNode 同类）");
        assertFalse(applier.report().hasStructuralErrors(), applier.report().structuralErrors().toString());
    }

    @Test
    @DisplayName("负向：propertyDocs 指向未注册/拼错的条目 schema 名 → unknownPropertySchemas 捕获（校验未削弱）")
    void listItemPropertyDocsUnknownSchemaStillFailsFast() {
        OpenAPI openApi = syntheticListDoc();
        Map<String, ApiDocEntry> entries = new LinkedHashMap<>();
        entries.put("GET /api/v1/synthetic/list", new ApiDocEntry(
                "Synthetic", "列出合成项", "列表分页语义",
                List.of(ParamDoc("limit", "query", "分页大小", "20", null),
                        ParamDoc("cursor", "query", "游标", null, null)),
                List.of(), null, null,
                List.of(ApiDocEntry.SuccessDoc.jsonList("200", "列表成功", SyntheticItem.class)),
                List.of(ErrorCode.RESOURCE_NOT_VISIBLE)));
        Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> badProps = Map.of(
                "SyntheticItemTypo", Map.of("id", ApiDocsCatalog.PropertyDoc.of("拼错的 schema 名")));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(entries, badProps,
                Map.of(), List.of(new Tag().name("Synthetic")))), MAPPER);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("unknownPropertySchemas"), ex.getMessage());
        assertTrue(applier.report().unknownPropertySchemas.contains("SyntheticItemTypo"));
        // 正确条目类型仍已注册（证明是"拼错名"被捕获，而非条目未注册这一不同原因）
        assertNotNull(openApi.getComponents().getSchemas().get("SyntheticItem"));
    }

    // ------------------------------------------------------------------ negative cases

    @Test
    @DisplayName("负向：目录键不存在于真实路由 → fail fast 并报告")
    void unknownCatalogKeyFailsFast() {
        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocEntry> entries = new LinkedHashMap<>(validCatalog().entries());
        entries.put("POST /api/v1/does-not-exist", validCatalog().entries()
                .get("POST /api/v1/synthetic/items"));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(entries,
                validCatalog().propertyDocs(), validCatalog().freeFormDocs(),
                List.of(new Tag().name("Synthetic")))), MAPPER);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("unknownCatalogKeys"));
        assertTrue(applier.report().unknownCatalogKeys.contains("POST /api/v1/does-not-exist"));
    }

    @Test
    @DisplayName("负向：跨目录键重复 → fail fast 并报告")
    void duplicateCatalogKeyFailsFast() {
        OpenAPI openApi = syntheticDoc();
        ApiDocsCatalog a = validCatalog();
        ApiDocsCatalog b = validCatalog();
        ApiDocsApplier applier = new ApiDocsApplier(List.of(a, b), MAPPER);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("duplicateCatalogKeys"));
        assertTrue(applier.report().duplicateCatalogKeys.contains("POST /api/v1/synthetic/items"));
    }

    @Test
    @DisplayName("负向：params 漏一个/多一个 → fail fast 并报告具体差异")
    void paramMismatchFailsFast() {
        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocEntry> entries = new LinkedHashMap<>(validCatalog().entries());
        // GET 真实参数为 itemId + limit；这里刻意漏掉 limit、多加 ghost
        entries.put("GET /api/v1/synthetic/items/{itemId}", new ApiDocEntry(
                "Synthetic", "查询", "参数不符", List.of(
                        ParamDoc("itemId", "path", "项 ID", null, null),
                        ParamDoc("ghost", "query", "多余参数", null, null)),
                List.of(), null, null,
                List.of(ApiDocEntry.SuccessDoc.json("200", "ok", SyntheticResult.class)),
                List.of(ErrorCode.RESOURCE_NOT_VISIBLE)));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(entries,
                Map.of(), Map.of(), List.of(new Tag().name("Synthetic")))), MAPPER);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("paramMismatches"));
        String mismatch = applier.report().paramMismatches.get(0);
        assertTrue(mismatch.contains("limit"), "应指出漏掉的真实参数: " + mismatch);
        assertTrue(mismatch.contains("ghost"), "应指出多余参数: " + mismatch);
    }

    @Test
    @DisplayName("负向：覆盖缺口不抛异常，但报告精确列出缺失操作（门禁数据来源）")
    void coverageGapReportedNotThrown() {
        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocEntry> onlyPost = Map.of(
                "POST /api/v1/synthetic/items", validCatalog().entries().get("POST /api/v1/synthetic/items"));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(onlyPost,
                Map.of(), Map.of(), List.of(new Tag().name("Synthetic")))), MAPPER);

        applier.customise(openApi); // 不抛
        assertFalse(applier.report().hasStructuralErrors());
        assertTrue(applier.report().missingOperations.contains("GET /api/v1/synthetic/items/{itemId}"));
        assertTrue(applier.report().missingOperations.contains("DELETE /api/v1/synthetic/items/{itemId}"));
        assertEquals(2, applier.report().missingOperations.size());
    }

    @Test
    @DisplayName("负向：propertyDocs/freeFormDocs 目标不存在 → fail fast 并报告")
    void unknownPropertyAndFreeFormTargetsFailFast() {
        OpenAPI openApi = syntheticDoc();
        Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> badProps = Map.of(
                "NoSuchSchema", Map.of("x", ApiDocsCatalog.PropertyDoc.of("x")));
        Map<String, ApiDocsCatalog.FreeFormDoc> badFree = Map.of(
                "SyntheticBody.nope", new ApiDocsCatalog.FreeFormDoc("x", Map.of(), true, null, null));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(
                validCatalog().entries(), badProps, badFree, List.of(new Tag().name("Synthetic")))), MAPPER);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("unknownPropertySchemas"));
        assertTrue(ex.getMessage().contains("unknownFreeFormTargets"));
    }

    // ------------------------------------------------------------------ fixtures

    private static ApiDocEntry.ParamDoc ParamDoc(String name, String in, String desc,
                                                 String example, Boolean requiredOverride) {
        return new ApiDocEntry.ParamDoc(name, in, desc, example, requiredOverride);
    }

    private static OpenAPI syntheticDoc() {
        Components components = new Components();
        components.addSchemas("Meta", new ObjectSchema()
                .addProperty("replayed", new io.swagger.v3.oas.models.media.BooleanSchema())
                .addProperty("serverTime", new StringSchema()));
        components.addSchemas("PrincipalContext", new ObjectSchema()
                .addProperty("principalType", new StringSchema())
                .addProperty("accountUuid", new StringSchema()));
        components.addSchemas("SuccessEnvelope", new ObjectSchema()
                .addProperty("requestId", new StringSchema())
                .addProperty("data", new ObjectSchema())
                .addProperty("meta", new Schema<>().$ref("#/components/schemas/Meta")));
        components.addSchemas("SyntheticBody", new ObjectSchema()
                .addProperty("name", new StringSchema())
                .addProperty("count", new IntegerSchema())
                .addProperty("state", new ObjectSchema())
                .addProperty("tags", new io.swagger.v3.oas.models.media.ArraySchema()
                        .items(new ObjectSchema())));

        Operation post = new Operation()
                .addParametersItem(new Parameter().name("Idempotency-Key").in("header")
                        .required(false).schema(new StringSchema()));
        // 模拟基线错误：multipart requestBody 被生成为 PrincipalContext
        post.setRequestBody(new RequestBody().content(new Content().addMediaType("multipart/form-data",
                new MediaType().schema(new Schema<>().$ref("#/components/schemas/PrincipalContext")))));
        post.setResponses(new ApiResponses().addApiResponse("200",
                new ApiResponse().description("OK")));

        Operation get = new Operation()
                .addParametersItem(new Parameter().name("itemId").in("path").required(true)
                        .schema(new StringSchema()))
                .addParametersItem(new Parameter().name("limit").in("query").required(false)
                        .schema(new IntegerSchema()));
        get.setResponses(new ApiResponses().addApiResponse("200",
                new ApiResponse().description("OK")));

        Operation delete = new Operation()
                .addParametersItem(new Parameter().name("itemId").in("path").required(true)
                        .schema(new StringSchema()))
                .addParametersItem(new Parameter().name("Idempotency-Key").in("header")
                        .required(false).schema(new StringSchema()));
        delete.setResponses(new ApiResponses().addApiResponse("200",
                new ApiResponse().description("OK")));

        Paths paths = new Paths();
        paths.addPathItem("/api/v1/synthetic/items", new PathItem().post(post));
        paths.addPathItem("/api/v1/synthetic/items/{itemId}", new PathItem().get(get).delete(delete));

        return new OpenAPI().components(components).paths(paths);
    }

    /** 列表端点合成文档：含一个不可达的 {@code ListData} 组件（应被修剪）。 */
    private static OpenAPI syntheticListDoc() {
        Components components = new Components();
        components.addSchemas("Meta", new ObjectSchema()
                .addProperty("replayed", new io.swagger.v3.oas.models.media.BooleanSchema())
                .addProperty("serverTime", new StringSchema()));
        components.addSchemas("ListData", new ObjectSchema()
                .addProperty("items", new io.swagger.v3.oas.models.media.ArraySchema())
                .addProperty("nextCursor", new StringSchema()));

        Operation get = new Operation()
                .addParametersItem(new Parameter().name("limit").in("query").required(false)
                        .schema(new IntegerSchema()))
                .addParametersItem(new Parameter().name("cursor").in("query").required(false)
                        .schema(new StringSchema()));
        get.setResponses(new ApiResponses().addApiResponse("200",
                new ApiResponse().description("OK")));

        Paths paths = new Paths();
        paths.addPathItem("/api/v1/synthetic/list", new PathItem().get(get));
        return new OpenAPI().components(components).paths(paths);
    }

    private static ApiDocsCatalog validCatalog() {
        Map<String, ApiDocEntry> entries = new LinkedHashMap<>();
        entries.put("POST /api/v1/synthetic/items", new ApiDocEntry(
                "Synthetic", "创建合成项",
                "多行说明：用途、鉴权、前置条件、幂等语义。",
                List.of(ParamDoc("Idempotency-Key", "header", "幂等键，1-128 字符", "key-1", true)),
                List.of(
                        ApiDocEntry.MultipartPartDoc.json("metadata", "metadata JSON（capture+consent）",
                                SyntheticMetadata.class),
                        ApiDocEntry.MultipartPartDoc.binary("face", "image/png", "人脸图，≤10MiB")),
                null, "multipart：metadata + face",
                List.of(ApiDocEntry.SuccessDoc.json("201", "创建成功", SyntheticResult.class),
                        ApiDocEntry.SuccessDoc.json("200", "幂等重放", SyntheticResult.class)),
                List.of(ErrorCode.INVALID_INPUT, ErrorCode.REQUEST_IN_PROGRESS,
                        ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT, ErrorCode.NOT_IMPLEMENTED)));
        entries.put("GET /api/v1/synthetic/items/{itemId}", new ApiDocEntry(
                "Synthetic", "查询合成项", "返回合成项详情与自由结构 state/tags。",
                List.of(ParamDoc("itemId", "path", "项 ID", null, null),
                        ParamDoc("limit", "query", "分页大小，默认 20、上限 100", "20", null)),
                List.of(), null, null,
                List.of(ApiDocEntry.SuccessDoc.json("200", "查询成功", SyntheticBody.class)),
                List.of(ErrorCode.RESOURCE_NOT_VISIBLE)));
        entries.put("DELETE /api/v1/synthetic/items/{itemId}", new ApiDocEntry(
                "Synthetic", "删除合成项", "删除后无响应体。",
                List.of(ParamDoc("itemId", "path", "项 ID", null, null),
                        ParamDoc("Idempotency-Key", "header", "幂等键", null, null)),
                List.of(), null, null,
                List.of(ApiDocEntry.SuccessDoc.noContent("204", "已删除，无响应体")),
                List.of(ErrorCode.RESOURCE_NOT_VISIBLE)));

        Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> props = new LinkedHashMap<>();
        props.put("Meta", Map.of(
                "replayed", ApiDocsCatalog.PropertyDoc.of("是否 T13 幂等重放"),
                "serverTime", new ApiDocsCatalog.PropertyDoc(
                        "服务端时间 RFC3339 UTC", null, null, "2026-09-13T08:30:00Z", "date-time")));
        props.put("SyntheticResult", Map.of(
                "id", ApiDocsCatalog.PropertyDoc.of("结果 ID", "r-1"),
                "value", ApiDocsCatalog.PropertyDoc.unitOf("数值", "次", "3")));

        Map<String, ApiDocsCatalog.FreeFormDoc> free = Map.of(
                "SyntheticBody.state", new ApiDocsCatalog.FreeFormDoc(
                        "设备状态（写入方：云台心跳）",
                        Map.of("power", "boolean: 是否开机", "mode", "string: 运行模式"),
                        true, "未来可新增键，客户端必须容忍；封闭键为 power/mode",
                        "{\"power\":true,\"mode\":\"idle\"}"));

        return new TestCatalog(entries, props, free, List.of(
                new Tag().name("Synthetic").description("合成域（单元测试）")));
    }

    private static Operation op(OpenAPI openApi, String path, PathItem.HttpMethod method) {
        return openApi.getPaths().get(path).readOperationsMap().get(method);
    }

    /** 合成目录。 */
    private record TestCatalog(Map<String, ApiDocEntry> entries,
                               Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> propertyDocs,
                               Map<String, ApiDocsCatalog.FreeFormDoc> freeFormDocs,
                               List<Tag> tags) implements ApiDocsCatalog {
        @Override
        public String domain() {
            return "synthetic";
        }

        @Override
        public Map<String, ApiDocEntry> entries() {
            return entries;
        }

        @Override
        public Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> propertyDocs() {
            return propertyDocs;
        }

        @Override
        public Map<String, ApiDocsCatalog.FreeFormDoc> freeFormDocs() {
            return freeFormDocs;
        }

        @Override
        public List<Tag> tags() {
            return new ArrayList<>(tags);
        }
    }
}

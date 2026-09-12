package cn.yuanxin.mvp.web.docs;

import cn.yuanxin.mvp.web.docs.catalog.ApiDocEntry;
import cn.yuanxin.mvp.web.docs.catalog.ApiDocsCatalog;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.core.converter.ModelConverters;
import io.swagger.v3.core.converter.ResolvedSchema;
import io.swagger.v3.core.util.Json31;
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
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

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

    public record SyntheticBody(String name, Integer count, Object state, List<Object> tags,
                                JsonNode blob) {
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

    // ------------------------------------------------------------------ multipart required / requiredProperties / unstructured detection

    @Test
    @DisplayName("BLOCKER1：multipart required 只含 required=true 的 part；properties/encoding 含全部 part")
    void multipartRequiredRespectsPartFlag() {
        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocEntry> entries = new LinkedHashMap<>(validCatalog().entries());
        entries.put("POST /api/v1/synthetic/items", new ApiDocEntry(
                "Synthetic", "创建合成项", "multipart 必填性按 part 指定",
                List.of(ParamDoc("Idempotency-Key", "header", "幂等键", "key-1", true)),
                List.of(
                        ApiDocEntry.MultipartPartDoc.json("metadata", "metadata", SyntheticMetadata.class, true),
                        ApiDocEntry.MultipartPartDoc.binary("front", "image/png",
                                "仅当 replacedViews 含 front 时必填", false),
                        ApiDocEntry.MultipartPartDoc.binary("left", "image/png",
                                "仅当 replacedViews 含 left 时必填", false),
                        ApiDocEntry.MultipartPartDoc.binary("right", "image/png",
                                "仅当 replacedViews 含 right 时必填", false)),
                null, "multipart",
                List.of(ApiDocEntry.SuccessDoc.json("201", "创建成功", SyntheticResult.class)),
                List.of(ErrorCode.INVALID_INPUT)));
        new ApiDocsApplier(List.of(new TestCatalog(entries, validCatalog().propertyDocs(),
                validCatalog().freeFormDocs(), List.of(new Tag().name("Synthetic")))), MAPPER)
                .customise(openApi);

        Operation post = op(openApi, "/api/v1/synthetic/items", PathItem.HttpMethod.POST);
        MediaType multipart = post.getRequestBody().getContent().get("multipart/form-data");
        Schema<?> schema = multipart.getSchema();
        assertEquals(List.of("metadata"), schema.getRequired(),
                "只有 required=true 的 part 进入 required");
        assertTrue(schema.getProperties().keySet().containsAll(
                List.of("metadata", "front", "left", "right")), "properties 含全部 part");
        assertEquals(Set.of("metadata", "front", "left", "right"), multipart.getEncoding().keySet(),
                "encoding 含全部 part");
    }

    @Test
    @DisplayName("IMPORTANT6：requiredProperties 合并进 schema.required；拼错 schema 名/属性名 → fail fast")
    void requiredPropertiesAppliedAndValidated() {
        // 正向：把 SyntheticResult.value 追加为必填
        OpenAPI openApi = syntheticDoc();
        Map<String, Set<String>> required = Map.of(
                "SyntheticResult", new LinkedHashSet<>(List.of("value")));
        new ApiDocsApplier(List.of(new TestCatalog(validCatalog().entries(), validCatalog().propertyDocs(),
                validCatalog().freeFormDocs(), List.of(new Tag().name("Synthetic")), required)), MAPPER)
                .customise(openApi);
        Schema<?> result = openApi.getComponents().getSchemas().get("SyntheticResult");
        assertNotNull(result.getRequired());
        assertTrue(result.getRequired().contains("value"), "requiredProperties 应合并进 required");

        // 负向：拼错 schema 名
        OpenAPI badSchemaDoc = syntheticDoc();
        ApiDocsApplier badSchema = new ApiDocsApplier(List.of(new TestCatalog(
                validCatalog().entries(), Map.of(), Map.of(),
                List.of(new Tag().name("Synthetic")),
                Map.of("NoSuchSchema", Set.of("x")))), MAPPER);
        IllegalStateException ex1 = assertThrows(IllegalStateException.class,
                () -> badSchema.customise(badSchemaDoc));
        assertTrue(ex1.getMessage().contains("unknownPropertySchemas"), ex1.getMessage());

        // 负向：属性名在该 schema 中不存在
        OpenAPI badPropDoc = syntheticDoc();
        ApiDocsApplier badProp = new ApiDocsApplier(List.of(new TestCatalog(
                validCatalog().entries(), Map.of(), Map.of(),
                List.of(new Tag().name("Synthetic")),
                Map.of("SyntheticResult", Set.of("nope")))), MAPPER);
        IllegalStateException ex2 = assertThrows(IllegalStateException.class,
                () -> badProp.customise(badPropDoc));
        assertTrue(ex2.getMessage().contains("unknownRequiredProperties"), ex2.getMessage());
    }

    @Test
    @DisplayName("IMPORTANT6：无结构对象检测（type=object 空壳 / $ref 空壳；有结构或指向有结构 schema 不误判）")
    void unstructuredObjectDetection() throws Exception {
        JsonNode schemas = MAPPER.readTree("{\"JsonNode\":{\"type\":\"object\"},"
                + "\"CaptureDto\":{\"type\":\"object\",\"properties\":{\"a\":{}}}}");
        assertTrue(ApiDocsApplier.isUnstructuredObject(
                MAPPER.readTree("{\"type\":\"object\"}"), schemas));
        assertTrue(ApiDocsApplier.isUnstructuredObject(
                MAPPER.readTree("{\"$ref\":\"#/components/schemas/JsonNode\"}"), schemas));
        assertFalse(ApiDocsApplier.isUnstructuredObject(
                MAPPER.readTree("{\"type\":\"object\",\"properties\":{\"a\":{}}}"), schemas));
        assertFalse(ApiDocsApplier.isUnstructuredObject(
                MAPPER.readTree("{\"type\":\"object\",\"additionalProperties\":true}"), schemas));
        assertFalse(ApiDocsApplier.isUnstructuredObject(
                MAPPER.readTree("{\"$ref\":\"#/components/schemas/CaptureDto\"}"), schemas));
        // 数组型自由结构：items 无结构对象亦为候选（如 HeartbeatBody.incidents）
        assertTrue(ApiDocsApplier.isUnstructuredObject(
                MAPPER.readTree("{\"type\":\"array\",\"items\":{\"type\":\"object\"}}"), schemas));
        assertFalse(ApiDocsApplier.isUnstructuredObject(
                MAPPER.readTree("{\"type\":\"array\",\"items\":{\"type\":\"object\","
                        + "\"properties\":{\"a\":{}}}}"), schemas));
    }

    // ------------------------------------------------------------------ structuredKeys (recursive) + gate hardening

    @Test
    @DisplayName("正向：structuredKeys 递归构建（array<closedObject>、mapOf 值 schema、any 不写 type）、与 knownKeys 并集且同名以 structured 为准、数组字段内层键作用于 items")
    void structuredKeysRecursiveBuildAndMerge() throws Exception {
        OpenAPI openApi = syntheticDoc();
        ApiDocsCatalog.KnownKeyDoc element = ApiDocsCatalog.KnownKeyDoc.closedObject(
                Map.of("a", ApiDocsCatalog.KnownKeyDoc.str("A 键"),
                        "b", ApiDocsCatalog.KnownKeyDoc.integer("B 键")),
                "元素对象");
        ApiDocsCatalog.KnownKeyDoc flex = new ApiDocsCatalog.KnownKeyDoc(
                "any", "标量或 {value,unit} 对象的联合", null, null, null, null, null);
        Map<String, Map<String, ApiDocsCatalog.KnownKeyDoc>> sk = Map.of(
                "SyntheticBody.state", Map.of(
                        "steps", ApiDocsCatalog.KnownKeyDoc.array(element, "步骤数组"),
                        "mapping", ApiDocsCatalog.KnownKeyDoc.mapOf(
                                ApiDocsCatalog.KnownKeyDoc.str("映射值"), "动态映射"),
                        "flex", flex,
                        "clash", ApiDocsCatalog.KnownKeyDoc.integer("结构化赢"),
                        "extra", ApiDocsCatalog.KnownKeyDoc.str("只有 structured 的键")),
                "SyntheticBody.tags", Map.of(
                        "detail", ApiDocsCatalog.KnownKeyDoc.opaqueObject("细节，未冻结")));
        Map<String, ApiDocsCatalog.FreeFormDoc> free = Map.of(
                "SyntheticBody.state", new ApiDocsCatalog.FreeFormDoc(
                        "状态", Map.of("keep", "boolean: 保留键", "clash", "string: 一层 DSL"),
                        true, "note", null),
                "SyntheticBody.tags", new ApiDocsCatalog.FreeFormDoc(
                        "标签", Map.of("code", "string: 码"), true, "note2", null));

        Map<String, ApiDocEntry> entries = new LinkedHashMap<>(validCatalog().entries());
        new ApiDocsApplier(List.of(new TestCatalog(entries, Map.of(), free,
                List.of(new Tag().name("Synthetic")), Map.of(), sk)), MAPPER).customise(openApi);

        Schema<?> body = openApi.getComponents().getSchemas().get("SyntheticBody");
        Schema<?> state = (Schema<?>) body.getProperties().get("state");
        assertEquals("object", state.getType());

        Schema<?> steps = (Schema<?>) state.getProperties().get("steps");
        assertEquals("array", steps.getType());
        Schema<?> stepItems = steps.getItems();
        assertEquals("object", stepItems.getType(), "array(closedObject) 必须生成 items.type=object");
        assertEquals(Boolean.FALSE, stepItems.getAdditionalProperties());
        assertNotNull(stepItems.getProperties().get("a"));
        assertEquals("integer", ((Schema<?>) stepItems.getProperties().get("b")).getType());

        Schema<?> mapping = (Schema<?>) state.getProperties().get("mapping");
        assertEquals("object", mapping.getType());
        assertTrue(mapping.getAdditionalProperties() instanceof Schema,
                "mapOf 的 additionalProperties 必须是<值 schema>而非布尔: "
                        + mapping.getAdditionalProperties());
        assertEquals("string", ((Schema<?>) mapping.getAdditionalProperties()).getType());

        Schema<?> flexSchema = (Schema<?>) state.getProperties().get("flex");
        assertNull(flexSchema.getType(), "any 不得写 type 关键字");
        assertTrue(flexSchema.getDescription().contains("联合"));

        assertEquals("boolean", ((Schema<?>) state.getProperties().get("keep")).getType(),
                "knownKeys 独有键应生效");
        assertEquals("integer", ((Schema<?>) state.getProperties().get("clash")).getType(),
                "同名键以 structuredKeys 为准");
        assertNotNull(state.getProperties().get("extra"), "只有 structuredKeys 的键应生效");

        // 数组型自由字段：内层键描述的是 items 对象的键
        Schema<?> tags = (Schema<?>) body.getProperties().get("tags");
        assertEquals("array", tags.getType());
        Schema<?> tagItems = tags.getItems();
        assertEquals("object", tagItems.getType());
        assertEquals("string", ((Schema<?>) tagItems.getProperties().get("code")).getType());
        Schema<?> detail = (Schema<?>) tagItems.getProperties().get("detail");
        assertNotNull(detail, "数组字段的 structuredKeys 内层键须作用于 items.properties");
        assertEquals("object", detail.getType());
        assertEquals(Boolean.TRUE, detail.getAdditionalProperties());

        // 序列化层（OpenAPI 3.1，与生产同源 Json31）：确认这些语义确实进入最终文档 JSON，
        // 而非只存在于内存对象（原 `$ref` 实例的 type 只设内存、不进 3.1 序列化）。
        JsonNode serState = MAPPER.readTree(Json31.mapper().writeValueAsString(openApi))
                .path("components").path("schemas").path("SyntheticBody")
                .path("properties").path("state");
        JsonNode serProps = serState.path("properties");
        assertFalse(serProps.path("flex").has("type"), "序列化层：any 不得写 type 关键字");
        assertTrue(serProps.path("flex").path("description").asText().contains("联合"),
                "序列化层：any 必须保留 description: " + serProps.path("flex"));
        assertTrue(serProps.path("mapping").path("additionalProperties").isObject(),
                "序列化层：mapOf 的 additionalProperties 必须是对象 schema 而非布尔");
        assertEquals("string",
                serProps.path("mapping").path("additionalProperties").path("type").asText());
        assertEquals("object", serProps.path("steps").path("items").path("type").asText());
        assertFalse(serProps.path("steps").path("items")
                .path("additionalProperties").asBoolean(true));
        assertEquals("integer", serProps.path("clash").path("type").asText());
    }

    @Test
    @DisplayName("负向：knownKeys 裸 array/object 前缀 → 结构性错误 fail fast（错误含字段路径）")
    void bareContainerKnownKeysFailFast() {
        // 裸 array
        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocsCatalog.FreeFormDoc> freeArray = Map.of(
                "SyntheticBody.state", new ApiDocsCatalog.FreeFormDoc(
                        "状态", Map.of("events", "array，事件列表"), true, "note", null));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(
                validCatalog().entries(), Map.of(), freeArray,
                List.of(new Tag().name("Synthetic")))), MAPPER);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("invalidKnownKeyTypes"), ex.getMessage());
        assertTrue(applier.report().invalidKnownKeyTypes.stream()
                        .anyMatch(p -> p.contains("SyntheticBody.state.events")),
                "错误必须含字段路径: " + applier.report().invalidKnownKeyTypes);

        // 裸 object
        OpenAPI openApi2 = syntheticDoc();
        Map<String, ApiDocsCatalog.FreeFormDoc> freeObject = Map.of(
                "SyntheticBody.state", new ApiDocsCatalog.FreeFormDoc(
                        "状态", Map.of("detail", "object，细节"), true, "note", null));
        ApiDocsApplier applier2 = new ApiDocsApplier(List.of(new TestCatalog(
                validCatalog().entries(), Map.of(), freeObject,
                List.of(new Tag().name("Synthetic")))), MAPPER);
        IllegalStateException ex2 = assertThrows(IllegalStateException.class,
                () -> applier2.customise(openApi2));
        assertTrue(ex2.getMessage().contains("invalidKnownKeyTypes"), ex2.getMessage());
        assertTrue(applier2.report().invalidKnownKeyTypes.stream()
                        .anyMatch(p -> p.contains("SyntheticBody.state.detail")),
                "错误必须含字段路径: " + applier2.report().invalidKnownKeyTypes);
    }

    @Test
    @DisplayName("正向：显式 array<string> 前缀生成 array<string>（真正的字符串数组）")
    void explicitStringArrayPrefixBuildsStringItems() throws Exception {
        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocsCatalog.FreeFormDoc> free = Map.of(
                "SyntheticBody.state", new ApiDocsCatalog.FreeFormDoc(
                        "状态", Map.of("regions", "array<string>，允许区域字符串数组"),
                        true, "note", null));
        new ApiDocsApplier(List.of(new TestCatalog(validCatalog().entries(), Map.of(), free,
                List.of(new Tag().name("Synthetic")))), MAPPER).customise(openApi);

        Schema<?> state = (Schema<?>) openApi.getComponents().getSchemas()
                .get("SyntheticBody").getProperties().get("state");
        Schema<?> regions = (Schema<?>) state.getProperties().get("regions");
        assertEquals("array", regions.getType());
        assertEquals("string", regions.getItems().getType());
        assertTrue(regions.getDescription().contains("区域"));

        // 序列化层（3.1）：array<string> 的 type/items.type 确实进入最终 JSON。
        JsonNode serRegions = MAPPER.readTree(Json31.mapper().writeValueAsString(openApi))
                .path("components").path("schemas").path("SyntheticBody")
                .path("properties").path("state").path("properties").path("regions");
        assertEquals("array", serRegions.path("type").asText());
        assertEquals("string", serRegions.path("items").path("type").asText());
    }

    @Test
    @DisplayName("负向：structuredKeys 的 array 缺 items → 引擎 fail fast")
    void structuredArrayWithoutItemsFailsFast() {
        OpenAPI openApi = syntheticDoc();
        ApiDocsCatalog.KnownKeyDoc badArray = new ApiDocsCatalog.KnownKeyDoc(
                "array", "坏数组（缺 items）", null, null, null, null, null);
        Map<String, Map<String, ApiDocsCatalog.KnownKeyDoc>> sk = Map.of(
                "SyntheticBody.state", Map.of("bad", badArray));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(
                validCatalog().entries(), Map.of(), Map.of(),
                List.of(new Tag().name("Synthetic")), Map.of(), sk)), MAPPER);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("items"), ex.getMessage());
    }

    @Test
    @DisplayName("负向：跨目录重复声明同一 structuredKeys 键 → fail fast 并报告")
    void duplicateStructuredKeysFailFast() {
        OpenAPI openApi = syntheticDoc();
        Map<String, Map<String, ApiDocsCatalog.KnownKeyDoc>> sk = Map.of(
                "SyntheticBody.state", Map.of("k", ApiDocsCatalog.KnownKeyDoc.str("x")));
        ApiDocsCatalog a = new TestCatalog(Map.of(), Map.of(), Map.of(),
                List.of(), Map.of(), sk);
        ApiDocsCatalog b = new TestCatalog(Map.of(), Map.of(), Map.of(),
                List.of(), Map.of(), sk);
        ApiDocsApplier applier = new ApiDocsApplier(List.of(a, b), MAPPER);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("duplicateStructuredKeys"), ex.getMessage());
        assertTrue(applier.report().duplicateStructuredKeys.contains("SyntheticBody.state.k"),
                applier.report().duplicateStructuredKeys.toString());
    }

    @Test
    @DisplayName("回归：清 $ref 展开自由结构后，OpenAPI 3.1 序列化结果必须带 type=object（JsonNode 型字段）")
    void refClearedFreeFormGetsObjectType() throws Exception {
        // 前置：证明 fixture 与真实文档同形。JsonNode 记录组件经 swagger 解析为 `$ref` 且无 type
        // （真实 SkinReportListItem.reportSummary / M4A04Metadata.reportedMicrocrystalState 同形），
        // 否则本回归不覆盖"清 `$ref`"路径，会退化为恒真。
        ResolvedSchema resolved =
                ModelConverters.getInstance().readAllAsResolvedSchema(SyntheticBody.class);
        Schema<?> before = (Schema<?>) resolved.schema.getProperties().get("blob");
        assertNotNull(before, "fixture 必须含 blob 字段");
        assertNotNull(before.get$ref(), "fixture 形态必须为 $ref（与真实 JsonNode 字段一致）");
        assertNull(before.getType(), "`$ref` 形态不得带 type");

        OpenAPI openApi = syntheticDoc();
        Map<String, ApiDocsCatalog.FreeFormDoc> free = Map.of(
                "SyntheticBody.blob", new ApiDocsCatalog.FreeFormDoc(
                        "JsonNode 型自由字段", Map.of("k", "string: 键"),
                        false, "封闭白名单", null));
        new ApiDocsApplier(List.of(new TestCatalog(validCatalog().entries(), Map.of(), free,
                List.of(new Tag().name("Synthetic")))), MAPPER).customise(openApi);

        // 与生产同源的序列化：生成的文档为 OpenAPI 3.1.0，springdoc 对 3.1 使用
        // io.swagger.v3.core.util.Json31.mapper()（其 Schema31Mixin 以 `types` 集合序列化 `type`）。
        JsonNode serialized = MAPPER.readTree(Json31.mapper().writeValueAsString(openApi))
                .path("components").path("schemas").path("SyntheticBody").path("properties").path("blob");
        assertFalse(serialized.has("$ref"), "展开后序列化结果不得含 $ref");
        assertTrue(serialized.has("type"),
                "序列化结果必须含 type 键：对原 $ref 实例原地 setType 不会进入 3.1 序列化");
        assertEquals("object", serialized.path("type").asText());
        assertEquals("string", serialized.path("properties").path("k").path("type").asText());
        assertFalse(serialized.path("additionalProperties").asBoolean(true),
                "additionalProperties 应为 false");

        // 内存态双保险（替换为 new ObjectSchema 后其构造器填充 type/types）。
        Schema<?> blob = (Schema<?>) openApi.getComponents().getSchemas()
                .get("SyntheticBody").getProperties().get("blob");
        assertNull(blob.get$ref(), "展开后不得保留 $ref");
        assertEquals("object", blob.getType(), "$ref 清除后必须带 type=object");

        // 负向判别力证明：对"原 $ref 实例只 setType、不替换实例"的同类节点，
        // 3.1 序列化结果确实缺 type ⇒ 证明上面的 "必须含 type" 断言能捕获原缺陷、不是恒真。
        Schema<?> refFormInstance = new Schema<>().$ref("#/components/schemas/JsonNode");
        refFormInstance.set$ref(null);
        refFormInstance.setType("object");
        JsonNode mutated = MAPPER.readTree(Json31.mapper().writeValueAsString(refFormInstance));
        assertFalse(mutated.has("type"),
                "原地 setType 于原 $ref 实例不得进入 3.1 序列化（本测试判别力的来源）");
    }

    @Test
    @DisplayName("门禁递归扫描：嵌套空 object / 无 type 的 items 必须失败；mapOf/核准不透明形态通过，且消息含完整路径")
    void recursiveStructureScanHasDiscriminatingPower() throws Exception {
        JsonNode nestedEmpty = MAPPER.readTree(
                "{\"Outer\":{\"type\":\"object\",\"properties\":{\"inner\":{\"type\":\"object\"}}}}");
        List<String> p1 = ApiDocsCoverageIT.findStructureProblems(nestedEmpty);
        assertFalse(p1.isEmpty(), "嵌套空 object 必须被递归发现");
        assertTrue(p1.get(0).contains("Outer.inner"), "消息须含完整路径: " + p1);

        JsonNode arrayBadItems = MAPPER.readTree(
                "{\"Outer\":{\"type\":\"array\",\"items\":{\"type\":\"object\"}}}");
        List<String> p2 = ApiDocsCoverageIT.findStructureProblems(arrayBadItems);
        assertFalse(p2.isEmpty(), "items 内部空 object 必须被发现");
        assertTrue(p2.get(0).contains("Outer[]"), "消息须含完整路径: " + p2);

        JsonNode arrayNoType = MAPPER.readTree("{\"Outer\":{\"type\":\"array\"}}");
        List<String> p3 = ApiDocsCoverageIT.findStructureProblems(arrayNoType);
        assertFalse(p3.isEmpty(), "array 缺 items 必须被发现");
        assertTrue(p3.get(0).contains("Outer"));

        JsonNode valid = MAPPER.readTree("{\"Outer\":{\"type\":\"object\",\"properties\":{"
                + "\"inner\":{\"type\":\"object\",\"additionalProperties\":true},"
                + "\"map\":{\"type\":\"object\",\"additionalProperties\":{\"type\":\"string\"}}}}}");
        assertTrue(ApiDocsCoverageIT.findStructureProblems(valid).isEmpty(),
                "有 additionalProperties 的形态不得误报: "
                        + ApiDocsCoverageIT.findStructureProblems(valid));
    }

    @Test
    @DisplayName("门禁 any 约束：未核准路径的无 type 节点必须失败；恰好三处方案参数映射值（含 steps[] 形态）通过")
    void unapprovedAnyNodeFailsGate() throws Exception {
        // 负向：未核准路径的 any（无 type、无 $ref、无 properties/additionalProperties）必须失败。
        JsonNode unapproved = MAPPER.readTree(
                "{\"Outer\":{\"type\":\"object\",\"properties\":{\"flex\":{\"description\":\"标量或对象联合\"}}}}");
        List<String> p = ApiDocsCoverageIT.findStructureProblems(unapproved);
        assertFalse(p.isEmpty(), "未核准的 any 节点必须被门禁发现");
        assertTrue(p.get(0).contains("Outer.flex"), "消息须含完整路径: " + p);

        // 正向：恰好三处方案参数映射值对应的 6 条真实路径（顶层 parameters.* 与 steps[].parameters.*）通过。
        JsonNode approved = MAPPER.readTree("{\"CarePlanFullView\":{\"type\":\"object\",\"properties\":{"
                + "\"plan\":{\"type\":\"object\",\"properties\":{"
                + "\"parameters\":{\"type\":\"object\",\"additionalProperties\":{\"description\":\"联合\"}},"
                + "\"steps\":{\"type\":\"array\",\"items\":{\"type\":\"object\",\"properties\":{"
                + "\"region\":{\"type\":\"string\"},"
                + "\"parameters\":{\"type\":\"object\",\"additionalProperties\":"
                + "{\"description\":\"联合\"}}}}}}}}}}");
        assertTrue(ApiDocsCoverageIT.findStructureProblems(approved).isEmpty(),
                "已核准的方案参数映射任何形态不得误报: "
                        + ApiDocsCoverageIT.findStructureProblems(approved));
    }

    // ------------------------------------------------------------------ nested required (BLOCKER A)

    @Test
    @DisplayName("BLOCKER-A 正向：嵌套 required 写入生成 schema，并经 OpenAPI 3.1 序列化输出；负向证明不施加时序列化确无 required")
    void nestedRequiredAppliedAndSerialized() throws Exception {
        OpenAPI openApi = syntheticDoc();
        ApiDocsCatalog.KnownKeyDoc element = ApiDocsCatalog.KnownKeyDoc.closedObject(
                Map.of("a", ApiDocsCatalog.KnownKeyDoc.str("A 键"),
                        "b", ApiDocsCatalog.KnownKeyDoc.str("B 键")),
                List.of("a"), "元素对象（required=[a]）");
        Map<String, Map<String, ApiDocsCatalog.KnownKeyDoc>> sk = Map.of(
                "SyntheticBody.state", Map.of(
                        "rows", ApiDocsCatalog.KnownKeyDoc.array(element, "行数组")));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(
                validCatalog().entries(), Map.of(), Map.of(),
                List.of(new Tag().name("Synthetic")), Map.of(), sk)), MAPPER);
        applier.customise(openApi);

        Schema<?> state = (Schema<?>) openApi.getComponents().getSchemas()
                .get("SyntheticBody").getProperties().get("state");
        Schema<?> rows = (Schema<?>) state.getProperties().get("rows");
        Schema<?> items = rows.getItems();
        assertEquals(List.of("a"), items.getRequired(), "嵌套 required 必须施加到 items（顺序按声明）");
        assertFalse(applier.report().hasStructuralErrors(), applier.report().structuralErrors().toString());

        // 序列化层（与生产同源 Json31，Schema31Mixin 以 types 集合序列化 type）；required 是
        // List<String>，无同类 mixin 忽略，但必须以序列化后的 JSON 为证据，不得只断言内存态。
        JsonNode serItems = MAPPER.readTree(Json31.mapper().writeValueAsString(openApi))
                .path("components").path("schemas").path("SyntheticBody")
                .path("properties").path("state").path("properties").path("rows").path("items");
        assertTrue(serItems.has("required"), "3.1 序列化结果必须含 required: " + serItems);
        assertEquals(1, serItems.path("required").size());
        assertEquals("a", serItems.path("required").get(0).asText());

        // 负向判别力：不调用 setRequired（修复前行为）时 3.1 序列化确实无 required，
        // 证明上面的"序列化必须含 required"断言能捕获原缺陷、不是恒真。
        ObjectSchema unfixed = new ObjectSchema();
        unfixed.addProperty("a", new StringSchema());
        JsonNode unfixedSer = MAPPER.readTree(Json31.mapper().writeValueAsString(unfixed));
        assertFalse(unfixedSer.has("required"),
                "未施加 required 时 3.1 序列化不含 required（本测试判别力来源）");
    }

    @Test
    @DisplayName("BLOCKER-A 负向：嵌套 required 含不在 properties 的名字 → 引擎 fail fast，报告含完整字段路径")
    void invalidNestedRequiredFailsFast() {
        OpenAPI openApi = syntheticDoc();
        ApiDocsCatalog.KnownKeyDoc bad = ApiDocsCatalog.KnownKeyDoc.closedObject(
                Map.of("a", ApiDocsCatalog.KnownKeyDoc.str("A 键")),
                List.of("a", "ghost"), "坏元素（ghost 不在 properties）");
        Map<String, Map<String, ApiDocsCatalog.KnownKeyDoc>> sk = Map.of(
                "SyntheticBody.state", Map.of(
                        "rows", ApiDocsCatalog.KnownKeyDoc.array(bad, "行数组")));
        ApiDocsApplier applier = new ApiDocsApplier(List.of(new TestCatalog(
                validCatalog().entries(), Map.of(), Map.of(),
                List.of(new Tag().name("Synthetic")), Map.of(), sk)), MAPPER);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> applier.customise(openApi));
        assertTrue(ex.getMessage().contains("invalidNestedRequired"), ex.getMessage());
        assertTrue(applier.report().hasStructuralErrors());
        assertTrue(applier.report().invalidNestedRequired.stream()
                        .anyMatch(p -> p.equals("SyntheticBody.state.rows[].ghost")),
                "错误必须含完整字段路径: " + applier.report().invalidNestedRequired);
    }

    // ------------------------------------------------------------------ inline contract pointer (BLOCKER B)

    @Test
    @DisplayName("BLOCKER-B：inline 契约 pointer 双向比对——相等通过；少于契约/多于 invent/pointer 失效皆被捕获")
    void inlineContractPointerComparisonHasDiscriminatingPower() {
        // 合成契约根，模拟 openapi.yaml 的 inline 节点形态（required 列表）。
        Map<String, Object> contract = new LinkedHashMap<>();
        Map<String, Object> schemas = new LinkedHashMap<>();
        Map<String, Object> image = new LinkedHashMap<>();
        image.put("required", List.of("mediaId", "contentUrl"));
        image.put("additionalProperties", false);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("properties", Map.of("image", image));
        schemas.put("View", view);
        contract.put("components", Map.of("schemas", schemas));
        String pointer = "/components/schemas/View/properties/image";

        // 正向：与契约逐字相等 → 通过。
        assertTrue(ApiDocsCoverageIT.crossCheckInlineRequired("Image", pointer,
                Set.of("mediaId", "contentUrl"), contract).isEmpty());

        // 负向①：生成侧为空集（修复前"跳过并打印"的形态）→ 必须被捕获，证明不是跳过就算过。
        List<String> missing = ApiDocsCoverageIT.crossCheckInlineRequired("Image", pointer,
                Set.of(), contract);
        assertFalse(missing.isEmpty());
        assertTrue(missing.get(0).contains("少于契约"), missing.toString());

        // 负向②：多于契约（invent）→ 失败。
        List<String> extra = ApiDocsCoverageIT.crossCheckInlineRequired("Image", pointer,
                Set.of("mediaId", "contentUrl", "ghost"), contract);
        assertFalse(extra.isEmpty());
        assertTrue(extra.get(0).contains("多于契约"), extra.toString());

        // 负向③：pointer 无法解析（映射表陈旧）→ 失败并披露，不静默通过。
        List<String> badPointer = ApiDocsCoverageIT.crossCheckInlineRequired("Image",
                "/components/schemas/NoSuch/properties/x", Set.of(), contract);
        assertFalse(badPointer.isEmpty());
        assertTrue(badPointer.get(0).contains("pointer 无法解析"), badPointer.toString());

        // resolvePointer 基本正确性（缺失段返回 null）。
        assertNull(ApiDocsCoverageIT.resolvePointer(contract, "/components/schemas/View/properties/no"));
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
    private static final class TestCatalog implements ApiDocsCatalog {
        private final Map<String, ApiDocEntry> entries;
        private final Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> propertyDocs;
        private final Map<String, ApiDocsCatalog.FreeFormDoc> freeFormDocs;
        private final List<Tag> tags;
        private final Map<String, Set<String>> requiredProperties;
        private final Map<String, Map<String, ApiDocsCatalog.KnownKeyDoc>> structuredKeys;

        private TestCatalog(Map<String, ApiDocEntry> entries,
                            Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> propertyDocs,
                            Map<String, ApiDocsCatalog.FreeFormDoc> freeFormDocs,
                            List<Tag> tags) {
            this(entries, propertyDocs, freeFormDocs, tags, Map.of(), Map.of());
        }

        private TestCatalog(Map<String, ApiDocEntry> entries,
                            Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> propertyDocs,
                            Map<String, ApiDocsCatalog.FreeFormDoc> freeFormDocs,
                            List<Tag> tags,
                            Map<String, Set<String>> requiredProperties) {
            this(entries, propertyDocs, freeFormDocs, tags, requiredProperties, Map.of());
        }

        private TestCatalog(Map<String, ApiDocEntry> entries,
                            Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> propertyDocs,
                            Map<String, ApiDocsCatalog.FreeFormDoc> freeFormDocs,
                            List<Tag> tags,
                            Map<String, Set<String>> requiredProperties,
                            Map<String, Map<String, ApiDocsCatalog.KnownKeyDoc>> structuredKeys) {
            this.entries = entries;
            this.propertyDocs = propertyDocs;
            this.freeFormDocs = freeFormDocs;
            this.tags = tags;
            this.requiredProperties = requiredProperties;
            this.structuredKeys = structuredKeys;
        }

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
        public Map<String, Set<String>> requiredProperties() {
            return requiredProperties;
        }

        @Override
        public Map<String, Map<String, ApiDocsCatalog.KnownKeyDoc>> structuredKeys() {
            return structuredKeys;
        }

        @Override
        public List<Tag> tags() {
            return new ArrayList<>(tags);
        }
    }
}

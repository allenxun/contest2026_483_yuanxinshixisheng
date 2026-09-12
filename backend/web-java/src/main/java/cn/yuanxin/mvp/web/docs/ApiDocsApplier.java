package cn.yuanxin.mvp.web.docs;

import cn.yuanxin.mvp.web.docs.catalog.ApiDocEntry;
import cn.yuanxin.mvp.web.docs.catalog.ApiDocsCatalog;
import cn.yuanxin.mvp.web.docs.catalog.ErrorCodeDocs;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.ErrorEnvelope;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.core.converter.ModelConverters;
import io.swagger.v3.core.converter.ResolvedSchema;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.headers.Header;
import io.swagger.v3.oas.models.media.ArraySchema;
import io.swagger.v3.oas.models.media.BooleanSchema;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.Encoding;
import io.swagger.v3.oas.models.media.IntegerSchema;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.NumberSchema;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.parameters.RequestBody;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import io.swagger.v3.oas.models.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.core.Ordered;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 集中式联调文档<strong>施加引擎</strong>：在 springdoc 从实际 Controller/DTO 生成 OpenAPI
 * 之后，把各 {@link ApiDocsCatalog} 提供的内容施加到生成对象上。它<strong>只改内存中的文档对象</strong>，
 * 不触碰任何控制器/DTO/业务代码，故序列化与业务行为零变更。
 *
 * <p>校验（fail fast）：目录键不得重复、必须对应真实 {@code METHOD path}、
 * {@code params} 必须与生成文档参数集合完全一致、propertyDocs/freeFormDocs 目标必须存在。
 * <strong>覆盖率</strong>（生成文档中未被任何目录覆盖的操作）只记录在 {@link Report}，
 * 不抛异常——这样四条目录道补齐期间 {@code /v3/api-docs} 仍可 200，而覆盖率门禁测试据
 * {@link Report} 精确指出缺失项。结构性错误（重复键/漂移键/参数不符/未知文档目标）则抛
 * {@link IllegalStateException}。</p>
 *
 * <p>执行顺序：本 bean 实现 {@link Ordered} 且 order 大于
 * {@link OpenApiDocsConfig} 的安全 customizer，从而在其（移除 {@code principal} 伪参数）
 * 之后施加；同时引擎自身在施加前<strong>幂等地</strong>再移除一次 {@code principal} 参数，
 * 保证不依赖顺序也正确。</p>
 */
public class ApiDocsApplier implements OpenApiCustomizer, Ordered {

    /** 在安全 customizer 之后执行。 */
    public static final int ORDER = 200;

    private static final Logger log = LoggerFactory.getLogger(ApiDocsApplier.class);

    private static final List<String> METHODS =
            List.of("get", "post", "put", "delete", "patch");
    private static final String SCHEMA_REF_PREFIX = "#/components/schemas/";
    private static final String REQUEST_ID_HEADER = "X-Request-Id";

    private final List<ApiDocsCatalog> catalogs;
    private final ObjectMapper objectMapper;
    private final Report report = new Report();

    public ApiDocsApplier(List<ApiDocsCatalog> catalogs, ObjectMapper objectMapper) {
        this.catalogs = catalogs == null ? List.of() : List.copyOf(catalogs);
        this.objectMapper = objectMapper;
    }

    @Override
    public int getOrder() {
        return ORDER;
    }

    /** 施加后的校验/覆盖率报告（供测试与日志）。 */
    public Report report() {
        return report;
    }

    @Override
    public void customise(OpenAPI openApi) {
        report.reset();
        Components components = openApi.getComponents() == null
                ? new Components() : openApi.getComponents();
        openApi.setComponents(components);
        if (components.getSchemas() == null) {
            components.setSchemas(new LinkedHashMap<>());
        }

        // 0) 幂等移除 principal 伪参数（既有安全 customizer 也会做；顺序无关地正确）。
        removePrincipalParameters(openApi);

        // 1) 合并目录。
        Map<String, ApiDocEntry> entries = new LinkedHashMap<>();
        Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> propertyDocs = new LinkedHashMap<>();
        Map<String, ApiDocsCatalog.FreeFormDoc> freeFormDocs = new LinkedHashMap<>();
        List<Tag> tags = new ArrayList<>();
        for (ApiDocsCatalog catalog : catalogs) {
            if (catalog.tags() != null) {
                tags.addAll(catalog.tags());
            }
            if (catalog.entries() != null) {
                for (Map.Entry<String, ApiDocEntry> e : catalog.entries().entrySet()) {
                    if (entries.putIfAbsent(e.getKey(), e.getValue()) != null) {
                        report.duplicateCatalogKeys.add(e.getKey());
                    }
                }
            }
            if (catalog.propertyDocs() != null) {
                for (Map.Entry<String, Map<String, ApiDocsCatalog.PropertyDoc>> s
                        : catalog.propertyDocs().entrySet()) {
                    Map<String, ApiDocsCatalog.PropertyDoc> merged =
                            propertyDocs.computeIfAbsent(s.getKey(), k -> new LinkedHashMap<>());
                    for (Map.Entry<String, ApiDocsCatalog.PropertyDoc> p : s.getValue().entrySet()) {
                        if (merged.putIfAbsent(p.getKey(), p.getValue()) != null) {
                            report.duplicatePropertyDocs.add(s.getKey() + "." + p.getKey());
                        }
                    }
                }
            }
            if (catalog.freeFormDocs() != null) {
                for (Map.Entry<String, ApiDocsCatalog.FreeFormDoc> f : catalog.freeFormDocs().entrySet()) {
                    if (freeFormDocs.putIfAbsent(f.getKey(), f.getValue()) != null) {
                        report.duplicateFreeFormDocs.add(f.getKey());
                    }
                }
            }
        }
        if (!tags.isEmpty()) {
            openApi.setTags(distinctTags(tags));
        }

        // 2) 真实路由（生成文档）。只统计对外 API 面（/api/**）：测试基础设施端点
        //    （如 /internal-test/**）不属于联调文档范围，不参与覆盖率门禁。
        Map<String, Operation> generated = new LinkedHashMap<>();
        if (openApi.getPaths() != null) {
            openApi.getPaths().forEach((path, item) -> {
                if (item == null || !path.startsWith("/api/")) {
                    return;
                }
                for (PathItem.HttpMethod m : PathItem.HttpMethod.values()) {
                    Operation op = item.readOperationsMap().get(m);
                    if (op != null) {
                        generated.put(m.name() + " " + path, op);
                    }
                }
            });
        }

        // 3) 结构校验：目录键必须对应真实路由。
        for (String key : entries.keySet()) {
            if (!generated.containsKey(key)) {
                report.unknownCatalogKeys.add(key);
            }
        }

        // 4) 施加操作级/参数/请求体/响应。
        Set<String> declaredTags = tags.stream().map(Tag::getName).collect(java.util.stream.Collectors.toSet());
        for (Map.Entry<String, ApiDocEntry> e : entries.entrySet()) {
            String key = e.getKey();
            Operation op = generated.get(key);
            if (op == null) {
                continue; // 已在 unknownCatalogKeys 记录
            }
            report.coveredOperations.add(key);
            applyEntry(key, op, e.getValue(), components, declaredTags);
        }

        // 5) 覆盖率（不抛异常，供门禁测试断言）。
        for (String key : generated.keySet()) {
            if (!report.coveredOperations.contains(key)) {
                report.missingOperations.add(key);
            }
        }

        // 6) 属性级文档（含响应 data 新注册的类型）。
        applyPropertyDocs(components, propertyDocs);

        // 7) 自由结构展开。
        applyFreeFormDocs(components, freeFormDocs);

        // 8) 清理不可达 schema（消除空壳 JsonNode / SuccessEnvelope / PrincipalContext 泄漏）。
        pruneUnreachableSchemas(openApi, components);

        // 9) 结构性错误 fail fast（覆盖率缺口不在此列）。
        if (report.hasStructuralErrors()) {
            String msg = "OpenAPI docs catalog validation failed: " + report.structuralErrors();
            log.error(msg);
            throw new IllegalStateException(msg);
        }
        log.info("OpenAPI docs applied: catalogs={} covered={}/{} missing={} prunedSchemas={}",
                catalogs.size(), report.coveredOperations.size(), generated.size(),
                report.missingOperations.size(), report.prunedSchemas);
    }

    // ------------------------------------------------------------------ entries

    private void applyEntry(String key, Operation op, ApiDocEntry entry, Components components,
                            Set<String> declaredTags) {
        if (entry.tag() != null) {
            op.setTags(new ArrayList<>(List.of(entry.tag())));
            if (!declaredTags.isEmpty() && !declaredTags.contains(entry.tag())) {
                report.undeclaredTags.add(key + " -> " + entry.tag());
            }
        }
        op.setSummary(entry.summary());
        op.setDescription(entry.description());

        applyParams(key, op, entry.params());
        applyRequestBody(entry, op, components);
        applySuccesses(key, op, entry, components);
        applyErrors(op, entry, components);
    }

    private void applyParams(String key, Operation op, List<ApiDocEntry.ParamDoc> params) {
        List<Parameter> actual = op.getParameters() == null ? List.of() : op.getParameters();
        Set<String> actualSet = new LinkedHashSet<>();
        for (Parameter p : actual) {
            actualSet.add(loc(p.getIn()) + ":" + p.getName());
        }
        Set<String> documentedSet = new LinkedHashSet<>();
        if (params != null) {
            for (ApiDocEntry.ParamDoc d : params) {
                documentedSet.add(loc(d.in()) + ":" + d.name());
            }
        }
        if (!actualSet.equals(documentedSet)) {
            Set<String> missing = new LinkedHashSet<>(actualSet);
            missing.removeAll(documentedSet);
            Set<String> extra = new LinkedHashSet<>(documentedSet);
            extra.removeAll(actualSet);
            report.paramMismatches.add(key + " missing=" + missing + " extra=" + extra);
            return;
        }
        if (params == null) {
            return;
        }
        for (ApiDocEntry.ParamDoc doc : params) {
            Parameter target = findParameter(actual, doc.name(), doc.in());
            if (target == null) {
                continue;
            }
            target.setDescription(doc.description());
            if (doc.example() != null) {
                target.setExample(coerceExample(doc.example(), target.getSchema()));
            }
            if (doc.requiredOverride() != null) {
                target.setRequired(doc.requiredOverride());
            }
        }
    }

    private void applyRequestBody(ApiDocEntry entry, Operation op, Components components) {
        List<ApiDocEntry.MultipartPartDoc> parts =
                entry.multipartParts() == null ? List.of() : entry.multipartParts();
        if (!parts.isEmpty()) {
            ObjectSchema multipart = new ObjectSchema();
            multipart.setDescription(entry.requestBodyDescription());
            Map<String, Encoding> encodings = new LinkedHashMap<>();
            List<String> required = new ArrayList<>();
            for (ApiDocEntry.MultipartPartDoc part : parts) {
                Schema<?> prop;
                if (part.jsonSchema() != null) {
                    String ref = registerType(part.jsonSchema(), components);
                    prop = new Schema<>().$ref(ref);
                } else {
                    String format = part.binaryFormat() == null ? "binary" : part.binaryFormat();
                    prop = new StringSchema().format(format);
                }
                prop.setDescription(part.description());
                multipart.addProperty(part.name(), prop);
                required.add(part.name());
                if (part.contentType() != null) {
                    Encoding encoding = new Encoding();
                    encoding.setContentType(part.contentType());
                    encodings.put(part.name(), encoding);
                }
            }
            multipart.setRequired(required);
            multipart.setAdditionalProperties(Boolean.FALSE);
            MediaType mediaType = new MediaType();
            mediaType.setSchema(multipart);
            if (!encodings.isEmpty()) {
                mediaType.setEncoding(encodings);
            }
            Content content = new Content();
            content.addMediaType("multipart/form-data", mediaType);
            op.setRequestBody(new RequestBody().required(true)
                    .description(entry.requestBodyDescription()).content(content));
        } else if (entry.requestBodyClass() != null) {
            String ref = registerType(entry.requestBodyClass(), components);
            Content content = new Content();
            content.addMediaType("application/json", new MediaType().schema(new Schema<>().$ref(ref)));
            op.setRequestBody(new RequestBody().required(true)
                    .description(entry.requestBodyDescription()).content(content));
        } else if (entry.requestBodyDescription() != null && op.getRequestBody() != null) {
            op.getRequestBody().setDescription(entry.requestBodyDescription());
        }
    }

    private void applySuccesses(String key, Operation op, ApiDocEntry entry, Components components) {
        List<ApiDocEntry.SuccessDoc> successes =
                entry.successes() == null ? List.of() : entry.successes();
        if (successes.isEmpty()) {
            report.emptySuccesses.add(key);
            return;
        }
        Set<String> codes = successes.stream().map(ApiDocEntry.SuccessDoc::code)
                .collect(java.util.stream.Collectors.toSet());
        ApiResponses responses = op.getResponses() == null ? new ApiResponses() : op.getResponses();
        // 移除 springdoc 占位 200（当该操作真实成功码不含 200）。
        if (!codes.contains("200")) {
            responses.remove("200");
        }
        for (ApiDocEntry.SuccessDoc doc : successes) {
            ApiResponse response = new ApiResponse().description(doc.description());
            response.addHeaderObject(REQUEST_ID_HEADER, requestIdHeader());
            // 四形态优先级：listItemClass > contentType > dataClass > 皆 null（204）。
            if (doc.listItemClass() != null) {
                Content content = new Content();
                content.addMediaType("application/json",
                        new MediaType().schema(listEnvelope(doc.listItemClass(), components)));
                response.setContent(content);
            } else if (doc.contentType() != null) {
                MediaType binary = new MediaType().schema(new StringSchema().format("binary"));
                Content content = new Content();
                content.addMediaType(doc.contentType(), binary);
                response.setContent(content);
            } else if (doc.dataClass() != null) {
                Content content = new Content();
                content.addMediaType("application/json",
                        new MediaType().schema(successEnvelope(doc.dataClass(), components)));
                response.setContent(content);
            }
            responses.addApiResponse(doc.code(), response);
        }
        op.setResponses(responses);
    }

    private void applyErrors(Operation op, ApiDocEntry entry, Components components) {
        List<ErrorCode> codes = entry.errorCodes() == null ? List.of() : entry.errorCodes();
        op.addExtension("x-error-codes",
                codes.stream().map(ErrorCode::name).collect(java.util.stream.Collectors.toList()));
        if (codes.isEmpty()) {
            return;
        }
        String errorRef = registerType(ErrorEnvelope.class, components);
        ApiResponses responses = op.getResponses() == null ? new ApiResponses() : op.getResponses();
        Set<String> successCodes = responses.keySet();
        Map<Integer, List<ErrorCode>> byStatus = new java.util.TreeMap<>();
        for (ErrorCode code : codes) {
            byStatus.computeIfAbsent(code.defaultStatus().value(), k -> new ArrayList<>()).add(code);
        }
        for (Map.Entry<Integer, List<ErrorCode>> e : byStatus.entrySet()) {
            String status = String.valueOf(e.getKey());
            if (successCodes.contains(status)) {
                continue; // 同状态已是成功响应，不覆盖
            }
            ApiResponse response = new ApiResponse().description(errorDescription(e.getValue()));
            response.addHeaderObject(REQUEST_ID_HEADER, requestIdHeader());
            Content content = new Content();
            content.addMediaType("application/json",
                    new MediaType().schema(new Schema<>().$ref(errorRef)));
            response.setContent(content);
            responses.addApiResponse(status, response);
        }
        op.setResponses(responses);
    }

    // ------------------------------------------------------------------ property / free-form

    private void applyPropertyDocs(Components components,
                                   Map<String, Map<String, ApiDocsCatalog.PropertyDoc>> propertyDocs) {
        for (Map.Entry<String, Map<String, ApiDocsCatalog.PropertyDoc>> schemaEntry
                : propertyDocs.entrySet()) {
            String schemaName = schemaEntry.getKey();
            Schema<?> schema = components.getSchemas().get(schemaName);
            if (schema == null) {
                report.unknownPropertySchemas.add(schemaName);
                continue;
            }
            Map<String, Schema> props = schema.getProperties();
            for (Map.Entry<String, ApiDocsCatalog.PropertyDoc> p : schemaEntry.getValue().entrySet()) {
                Schema<?> prop = props == null ? null : (Schema<?>) props.get(p.getKey());
                if (prop == null) {
                    report.unknownPropertyNames.add(schemaName + "." + p.getKey());
                    continue;
                }
                applyPropertyDoc(prop, p.getValue());
            }
        }
    }

    private static void applyPropertyDoc(Schema<?> prop, ApiDocsCatalog.PropertyDoc doc) {
        String description = doc.description();
        if (doc.unit() != null && !doc.unit().isBlank()) {
            description = description + "（单位：" + doc.unit() + "）";
        }
        prop.setDescription(description);
        if (doc.allowedValues() != null && !doc.allowedValues().isEmpty()) {
            @SuppressWarnings({"unchecked", "rawtypes"})
            Schema raw = prop;
            raw.setEnum(new ArrayList<>(doc.allowedValues()));
            if (prop.getType() == null) {
                prop.setType("string");
            }
        }
        if (doc.example() != null) {
            prop.setExample(coerceExample(doc.example(), prop));
        }
        if (doc.format() != null) {
            prop.setFormat(doc.format());
        }
    }

    private void applyFreeFormDocs(Components components,
                                   Map<String, ApiDocsCatalog.FreeFormDoc> freeFormDocs) {
        for (Map.Entry<String, ApiDocsCatalog.FreeFormDoc> e : freeFormDocs.entrySet()) {
            String key = e.getKey();
            int dot = key.indexOf('.');
            if (dot <= 0 || dot == key.length() - 1) {
                report.unknownFreeFormTargets.add(key + " (key 必须为 SchemaName.propertyName)");
                continue;
            }
            String schemaName = key.substring(0, dot);
            String propName = key.substring(dot + 1);
            Schema<?> schema = components.getSchemas().get(schemaName);
            Schema<?> prop = schema == null || schema.getProperties() == null
                    ? null : (Schema<?>) schema.getProperties().get(propName);
            if (prop == null) {
                report.unknownFreeFormTargets.add(key);
                continue;
            }
            applyFreeForm(prop, e.getValue());
        }
    }

    @SuppressWarnings("unchecked")
    private void applyFreeForm(Schema<?> prop, ApiDocsCatalog.FreeFormDoc doc) {
        boolean array = "array".equals(prop.getType()) || prop.getItems() != null;
        boolean opaque = isExplicitOpaqueDeclaration(doc);
        String description = opaque ? opaqueDescription(doc) : structureDescription(doc);
        ObjectSchema struct = new ObjectSchema();
        Map<String, Schema> properties = new LinkedHashMap<>();
        if (!opaque && doc.knownKeys() != null) {
            for (Map.Entry<String, String> k : doc.knownKeys().entrySet()) {
                properties.put(k.getKey(), keySchema(k.getValue()));
            }
        }
        struct.setProperties(properties);
        struct.setAdditionalProperties(doc.extensible());
        struct.setDescription(description);
        if (doc.example() != null) {
            Object example = parseJsonExample(doc.example());
            if (example != null) {
                struct.setExample(example);
            }
        }
        prop.setDescription(description);
        if (array) {
            prop.setItems(struct);
        } else {
            prop.setType("object");
            prop.setProperties(properties);
            prop.setAdditionalProperties(doc.extensible());
            if (struct.getExample() != null) {
                prop.setExample(struct.getExample());
            }
        }
    }

    /**
     * 显式不透明声明判定（现有字段取值约定，不改冻结接口）：{@code knownKeys} 为空（或 null）
     * <b>且</b> {@code extensibilityNote} 非空 ⇒ 该字段是诚实的不透明开放对象（现实中存在零已知键、
     * 且服务端当前不消费的自由结构，如 {@code AppSessionRequestBody.installBindingMaterial}）。
     * {@code knownKeys} 非空 ⇒ 按现状展开为显式 properties。<b>两者皆缺（空 knownKeys + 空 note）
     * 不构成声明</b>，仍产出开放对象但门禁会据描述判定为未声明。
     */
    static boolean isExplicitOpaqueDeclaration(ApiDocsCatalog.FreeFormDoc doc) {
        boolean noKnownKeys = doc.knownKeys() == null || doc.knownKeys().isEmpty();
        boolean hasNote = doc.extensibilityNote() != null && !doc.extensibilityNote().isBlank();
        return noKnownKeys && hasNote;
    }

    /**
     * 显式不透明声明的<strong>规范标记</strong>：只有真正走不透明分支
     * （{@link #isExplicitOpaqueDeclaration} = 零已知键 + 非空 {@code extensibilityNote}）
     * 的字段才会带上它，因此它可以作为门禁的<strong>可靠判据</strong>。
     */
    public static final String OPAQUE_MARKER = "【显式不透明对象】";

    /** 不透明对象描述：显式不透明/未冻结声明 + 原 description 与 extensibilityNote（不改其语义）。 */
    private static String opaqueDescription(ApiDocsCatalog.FreeFormDoc doc) {
        return OPAQUE_MARKER + "本字段为开放结构、未冻结，已知键集合为空；"
                + "客户端不得依赖任何具体键名，也不得假设字段存在。\n" + structureDescription(doc);
    }

    private static String structureDescription(ApiDocsCatalog.FreeFormDoc doc) {
        String base = doc.description() == null ? "" : doc.description();
        if (doc.extensibilityNote() != null && !doc.extensibilityNote().isBlank()) {
            base = base + "\n可扩展边界：" + doc.extensibilityNote();
        }
        return base;
    }

    /** 自由结构字段的门禁判定结果（生成文档 JSON 视角）。 */
    public enum FreeFormGate {
        /** 已展开为显式 properties（含 {@code array.items.properties}）。 */
        EXPANDED,
        /** 显式不透明声明：描述含不透明/未冻结表述，且显式设置了 additionalProperties。 */
        EXPLICIT_OPAQUE,
        /** 描述有声明，但未显式设置 additionalProperties。 */
        OPAQUE_MISSING_ADDITIONAL_PROPERTIES,
        /** 既无 properties 也无显式不透明声明（裸 {@code {type: object}}）。 */
        NOT_DECLARED
    }

    /**
     * 判定生成文档中某自由结构字段是否符合门禁（门禁测试的唯一事实来源）。
     * <b>不弱化意图</b>：裸 {@code {type:object}} 仍为 {@link FreeFormGate#NOT_DECLARED}；
     * 只有"显式展开 properties"或"显式不透明声明（描述 + additionalProperties）"才通过。
     */
    public static FreeFormGate classifyFreeForm(JsonNode prop) {
        if (prop == null || prop.isMissingNode()) {
            return FreeFormGate.NOT_DECLARED;
        }
        boolean array = "array".equals(prop.path("type").asText());
        JsonNode target = array && prop.has("items") ? prop.path("items") : prop;
        boolean hasProperties = prop.path("properties").size() > 0
                || (array && target.path("properties").size() > 0);
        if (hasProperties) {
            return FreeFormGate.EXPANDED;
        }
        String desc = target.path("description").asText("");
        // 只认引擎注入的规范标记 OPAQUE_MARKER，不再做自由文本关键词匹配：
        // 关键词匹配不可靠——合法描述里出现"未冻结""不透明"等字样（例如"普通数组描述
        // （无任何不透明/未冻结表述）"）会被误判为已声明，使"零已知键且零说明"的字段蒙混过关。
        boolean declaresOpaque = desc.contains(OPAQUE_MARKER);
        boolean hasAdditional = target.has("additionalProperties");
        if (declaresOpaque && hasAdditional) {
            return FreeFormGate.EXPLICIT_OPAQUE;
        }
        if (declaresOpaque) {
            return FreeFormGate.OPAQUE_MISSING_ADDITIONAL_PROPERTIES;
        }
        return FreeFormGate.NOT_DECLARED;
    }

    /**
     * knownKeys 值约定：以 JSON 类型开头（{@code integer}/{@code number}/{@code boolean}/
     * {@code object}/{@code array}/{@code string}），后接分隔符与中文说明，例如
     * {@code "integer，目标次数 N，单位：次"}；无类型前缀时默认 {@code string}。
     */
    private static Schema<?> keySchema(String text) {
        String type = "string";
        String desc = text == null ? "" : text;
        if (text != null) {
            String lower = text.toLowerCase(Locale.ROOT);
            for (String cand : List.of("integer", "number", "boolean", "object", "array", "string")) {
                if (lower.startsWith(cand)) {
                    type = cand;
                    desc = text.substring(cand.length()).replaceFirst("^[\\s:：,，\\-]+", "");
                    break;
                }
            }
        }
        Schema<?> schema = switch (type) {
            case "integer" -> new IntegerSchema();
            case "number" -> new NumberSchema();
            case "boolean" -> new BooleanSchema();
            case "object" -> new ObjectSchema();
            case "array" -> new ArraySchema().items(new StringSchema());
            default -> new StringSchema();
        };
        if (!desc.isBlank()) {
            schema.setDescription(desc);
        }
        return schema;
    }

    // ------------------------------------------------------------------ helpers

    private Schema<?> successEnvelope(Class<?> dataClass, Components components) {
        String dataRef = registerType(dataClass, components);
        return envelope(new Schema<>().$ref(dataRef), "业务数据；字段含义见该类型定义", components);
    }

    /**
     * 列表响应 data 形状（{@code ListData<T>}）：{@code {items:[条目类型], nextCursor:string|null}}。
     *
     * <p>条目类型经 {@link #registerType} 注册进 {@code components.schemas}（其字段因此可由
     * {@code propertyDocs} 文档化）；对条目类型的 {@code $ref} 位于<strong>内联</strong> data schema
     * 的 {@code items} 内，修剪逻辑的可达性遍历会走入内联 properties/items，故不会被误删。</p>
     */
    private Schema<?> listEnvelope(Class<?> itemClass, Components components) {
        String itemRef = registerType(itemClass, components);
        ObjectSchema listData = new ObjectSchema();
        listData.setDescription("列表数据（ListData<T>）：{items, nextCursor}");
        ArraySchema items = new ArraySchema();
        items.setItems(new Schema<>().$ref(itemRef));
        items.setDescription("本页条目数组。分页 limit 默认 20、上限 100；cursor 为 keyset 游标"
                + "（不透明、原样回传；非法游标 400 INVALID_INPUT，details.reason=invalid_cursor）");
        listData.addProperty("items", items);
        StringSchema nextCursor = new StringSchema();
        nextCursor.setDescription("下一页游标；为 null 表示无后续页（字段保留，不省略）");
        nextCursor.setNullable(Boolean.TRUE);
        listData.addProperty("nextCursor", nextCursor);
        listData.setRequired(new ArrayList<>(List.of("items")));
        return envelope(listData, "列表数据；条目结构见 items.$ref", components);
    }

    /** 构造统一成功信封 {@code {requestId, data, meta}}，{@code data} 可内联成任意 schema。 */
    private Schema<?> envelope(Schema<?> dataSchema, String dataDescription, Components components) {
        ensureSchema(components, "Meta", SuccessEnvelope.Meta.class);
        ObjectSchema envelope = new ObjectSchema();
        envelope.setDescription("统一成功信封 {requestId, data, meta}；204 无响应体");
        envelope.addProperty("requestId", new StringSchema()
                .description("本次 HTTP 尝试的请求 ID，与响应头 X-Request-Id 同值；"
                        + "每次重试都会变化，不能用作幂等键")
                .example("0e6a2b1c-4d5e-6f70-8a9b-0c1d2e3f4a5b"));
        envelope.addProperty("data", dataSchema.description(dataDescription));
        envelope.addProperty("meta", new Schema<>().$ref(SCHEMA_REF_PREFIX + "Meta")
                .description("元数据：replayed=是否 T13 幂等重放（true 时未重做写入）；"
                        + "serverTime=服务端时间 RFC3339 UTC 秒精度"));
        envelope.setRequired(new ArrayList<>(List.of("requestId", "data", "meta")));
        return envelope;
    }

    private String registerType(Class<?> clazz, Components components) {
        ResolvedSchema resolved = ModelConverters.getInstance().readAllAsResolvedSchema(clazz);
        if (resolved.referencedSchemas != null) {
            resolved.referencedSchemas.forEach(components::addSchemas);
        }
        Schema<?> schema = resolved.schema;
        if (schema != null && schema.get$ref() != null) {
            return schema.get$ref();
        }
        String name = clazz.getSimpleName();
        if (schema != null) {
            components.addSchemas(name, schema);
        }
        return SCHEMA_REF_PREFIX + name;
    }

    private static void ensureSchema(Components components, String name, Class<?> clazz) {
        if (components.getSchemas() != null && components.getSchemas().containsKey(name)) {
            return;
        }
        ResolvedSchema resolved = ModelConverters.getInstance().readAllAsResolvedSchema(clazz);
        if (resolved.referencedSchemas != null) {
            resolved.referencedSchemas.forEach(components::addSchemas);
        }
        if (resolved.schema != null && resolved.schema.get$ref() == null) {
            components.addSchemas(name, resolved.schema);
        }
    }

    private static Header requestIdHeader() {
        return new Header().description("本次 HTTP 尝试的请求 ID，与响应体 requestId 同值");
    }

    private static String errorDescription(List<ErrorCode> codes) {
        StringBuilder sb = new StringBuilder("业务错误（HTTP 状态由各业务码映射；同一状态多码合并列出）：");
        for (ErrorCode code : codes) {
            sb.append("\n- ").append(code.name())
                    .append("（retryable=").append(code.defaultRetryable()).append("）：")
                    .append(ErrorCodeDocs.describe(code));
        }
        return sb.toString();
    }

    private static Object coerceExample(String example, Schema<?> schema) {
        String type = schema == null ? null : schema.getType();
        if (type == null && schema != null && schema.getEnum() != null) {
            type = "string";
        }
        if ("integer".equals(type)) {
            try {
                return Long.valueOf(example.trim());
            } catch (NumberFormatException ignored) {
                return example;
            }
        }
        if ("number".equals(type)) {
            try {
                return Double.valueOf(example.trim());
            } catch (NumberFormatException ignored) {
                return example;
            }
        }
        if ("boolean".equals(type)) {
            return Boolean.valueOf(example.trim());
        }
        return example;
    }

    private Object parseJsonExample(String example) {
        try {
            JsonNode node = objectMapper.readTree(example);
            return objectMapper.convertValue(node, Object.class);
        } catch (Exception e) {
            return example;
        }
    }

    private static Parameter findParameter(List<Parameter> params, String name, String in) {
        for (Parameter p : params) {
            if (name.equals(p.getName()) && (in == null || loc(p.getIn()).equals(loc(in)))) {
                return p;
            }
        }
        return null;
    }

    private static String loc(String in) {
        return in == null ? "" : in.toLowerCase(Locale.ROOT);
    }

    private static List<Tag> distinctTags(List<Tag> tags) {
        Map<String, Tag> byName = new LinkedHashMap<>();
        for (Tag tag : tags) {
            byName.putIfAbsent(tag.getName(), tag);
        }
        return new ArrayList<>(byName.values());
    }

    private static void removePrincipalParameters(OpenAPI openApi) {
        if (openApi.getPaths() == null) {
            return;
        }
        openApi.getPaths().forEach((path, item) -> {
            if (item == null) {
                return;
            }
            for (Operation op : item.readOperationsMap().values()) {
                if (op.getParameters() == null) {
                    continue;
                }
                List<Parameter> kept = new ArrayList<>();
                for (Parameter p : op.getParameters()) {
                    if (!"principal".equals(p.getName())) {
                        kept.add(p);
                    }
                }
                op.setParameters(kept.isEmpty() ? null : kept);
            }
        });
    }

    // ------------------------------------------------------------------ prune

    private void pruneUnreachableSchemas(OpenAPI openApi, Components components) {
        if (components.getSchemas() == null || components.getSchemas().isEmpty()) {
            return;
        }
        Set<String> reachable = reachableSchemaNames(openApi);
        List<String> remove = new ArrayList<>();
        for (String name : new ArrayList<>(components.getSchemas().keySet())) {
            if (!reachable.contains(name)) {
                remove.add(name);
            }
        }
        for (String name : remove) {
            components.getSchemas().remove(name);
            report.prunedSchemas.add(name);
        }
    }

    private Set<String> reachableSchemaNames(OpenAPI openApi) {
        Map<String, Schema> schemas = openApi.getComponents() == null
                ? Map.of() : openApi.getComponents().getSchemas();
        if (schemas == null) {
            schemas = Map.of();
        }
        Deque<String> queue = new ArrayDeque<>();
        collectRefs(openApi.getPaths(), queue);
        Components c = openApi.getComponents();
        if (c != null) {
            collectRefs(c.getResponses(), queue);
            collectRefs(c.getParameters(), queue);
            collectRefs(c.getRequestBodies(), queue);
            collectRefs(c.getHeaders(), queue);
        }
        Set<String> reachable = new LinkedHashSet<>();
        Set<String> visited = new HashSet<>();
        while (!queue.isEmpty()) {
            String name = queue.poll();
            if (!visited.add(name)) {
                continue;
            }
            Schema<?> schema = schemas.get(name);
            if (schema == null) {
                continue;
            }
            reachable.add(name);
            collectRefs(schema, queue);
        }
        return reachable;
    }

    private void collectRefs(Object node, Deque<String> out) {
        if (node == null) {
            return;
        }
        collectRefs(objectMapper.valueToTree(node), out);
    }

    private static void collectRefs(JsonNode node, Deque<String> out) {
        if (node == null) {
            return;
        }
        if (node.isObject()) {
            JsonNode ref = node.get("$ref");
            if (ref != null && ref.isTextual() && ref.asText().startsWith(SCHEMA_REF_PREFIX)) {
                out.add(ref.asText().substring(SCHEMA_REF_PREFIX.length()));
            }
            node.fields().forEachRemaining(e -> collectRefs(e.getValue(), out));
        } else if (node.isArray()) {
            node.forEach(child -> collectRefs(child, out));
        }
    }

    // ------------------------------------------------------------------ report

    /** 施加过程的校验/覆盖率报告。 */
    public static final class Report {
        public final List<String> unknownCatalogKeys = new ArrayList<>();
        public final List<String> duplicateCatalogKeys = new ArrayList<>();
        public final List<String> missingOperations = new ArrayList<>();
        public final List<String> paramMismatches = new ArrayList<>();
        public final List<String> emptySuccesses = new ArrayList<>();
        public final List<String> unknownPropertySchemas = new ArrayList<>();
        public final List<String> unknownPropertyNames = new ArrayList<>();
        public final List<String> duplicatePropertyDocs = new ArrayList<>();
        public final List<String> unknownFreeFormTargets = new ArrayList<>();
        public final List<String> duplicateFreeFormDocs = new ArrayList<>();
        public final List<String> undeclaredTags = new ArrayList<>();
        public final Set<String> coveredOperations = new LinkedHashSet<>();
        public final Set<String> prunedSchemas = new LinkedHashSet<>();

        void reset() {
            unknownCatalogKeys.clear();
            duplicateCatalogKeys.clear();
            missingOperations.clear();
            paramMismatches.clear();
            emptySuccesses.clear();
            unknownPropertySchemas.clear();
            unknownPropertyNames.clear();
            duplicatePropertyDocs.clear();
            unknownFreeFormTargets.clear();
            duplicateFreeFormDocs.clear();
            undeclaredTags.clear();
            coveredOperations.clear();
            prunedSchemas.clear();
        }

        public boolean hasStructuralErrors() {
            return !unknownCatalogKeys.isEmpty() || !duplicateCatalogKeys.isEmpty()
                    || !paramMismatches.isEmpty() || !emptySuccesses.isEmpty()
                    || !unknownPropertySchemas.isEmpty() || !unknownPropertyNames.isEmpty()
                    || !duplicatePropertyDocs.isEmpty() || !unknownFreeFormTargets.isEmpty()
                    || !duplicateFreeFormDocs.isEmpty();
        }

        public List<String> structuralErrors() {
            List<String> errors = new ArrayList<>();
            if (!unknownCatalogKeys.isEmpty()) {
                errors.add("unknownCatalogKeys(生成文档中不存在)=" + unknownCatalogKeys);
            }
            if (!duplicateCatalogKeys.isEmpty()) {
                errors.add("duplicateCatalogKeys=" + duplicateCatalogKeys);
            }
            if (!paramMismatches.isEmpty()) {
                errors.add("paramMismatches=" + paramMismatches);
            }
            if (!emptySuccesses.isEmpty()) {
                errors.add("emptySuccesses=" + emptySuccesses);
            }
            if (!unknownPropertySchemas.isEmpty()) {
                errors.add("unknownPropertySchemas=" + unknownPropertySchemas);
            }
            if (!unknownPropertyNames.isEmpty()) {
                errors.add("unknownPropertyNames=" + unknownPropertyNames);
            }
            if (!duplicatePropertyDocs.isEmpty()) {
                errors.add("duplicatePropertyDocs=" + duplicatePropertyDocs);
            }
            if (!unknownFreeFormTargets.isEmpty()) {
                errors.add("unknownFreeFormTargets=" + unknownFreeFormTargets);
            }
            if (!duplicateFreeFormDocs.isEmpty()) {
                errors.add("duplicateFreeFormDocs=" + duplicateFreeFormDocs);
            }
            return errors;
        }
    }
}

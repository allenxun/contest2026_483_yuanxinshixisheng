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

    /**
     * 经 orchestrator 审议核准的 {@code any} 节点路径（无 {@code type}、无 {@code $ref}、无
     * {@code properties}/{@code additionalProperties}）。只允许<strong>恰好这三处</strong>方案参数映射的值
     * （依据写入方 {@code CarePlanProjection.projectParameter}：参数值真实存在"标量 或
     * {@code {value,unit}} 对象"的联合形态）。路径按 {@link #scanStructure} 的递归扫描格式：
     *
     * <pre>
     * CarePlanFullView.plan.parameters.*
     * CarePlanFullView.plan.steps[].parameters.*
     * CareExecutionAdmission.planExecution.parameters.*
     * CareExecutionAdmission.planExecution.steps[].parameters.*
     * CareExecutionRevalidation.planExecution.parameters.*
     * CareExecutionRevalidation.planExecution.steps[].parameters.*
     * </pre>
     *
     * <p>三处方案结构各自出现两个 {@code any} 节点（顶层 {@code parameters.*} 与步骤内
     * {@code steps[].parameters.*}，二者共用同一 {@code KnownKeyDoc.any} 定义），故清单共 6 条路径，
     * 恰等于真实文档中出现的 6 个 {@code any} 节点，不多不少。任何其它路径上的 {@code any}
     * 一律失败——防止 <strong>用 {@code any} 绕过"对象/数组结构必须显式声明"的递归门禁</strong>。
     * 协议最终冻结时应把这三处改为 {@code oneOf}，届时本清单随之删除。</p>
     *
     * <p><b>匹配规则</b>：采用<strong>精确成员判定</strong>（{@code APPROVED_ANY_PATHS.contains(path)}），
     * 而非"以 {@code .parameters.*} 结尾且前缀含 {@code .plan.}/{@code .planExecution.}"式模式匹配——
     * 后者会顺带放行未来任何 {@code *plan*.parameters.*} 路径。精确集合由上述三处结构<strong>逐字</strong>
     * 推导，新增/改名任一结构都会使门禁失败并暴露待审路径，不会静默放行。</p>
     */
    private static final Set<String> APPROVED_ANY_PATHS = Set.of(
            "CarePlanFullView.plan.parameters.*",
            "CarePlanFullView.plan.steps[].parameters.*",
            "CareExecutionAdmission.planExecution.parameters.*",
            "CareExecutionAdmission.planExecution.steps[].parameters.*",
            "CareExecutionRevalidation.planExecution.parameters.*",
            "CareExecutionRevalidation.planExecution.steps[].parameters.*");

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

    /**
     * 生成 schema 名 → 契约 components schema 名，用于<strong>成功响应 data</strong> 侧
     * required 交叉校验。每条的取证来源：
     * <ul>
     *   <li>同名映射（下列未列出的响应类型）：{@code openapi.yaml components.schemas} 与 DTO
     *       简单类名同名，如 {@code MemberAccessGrantResult}、{@code AssessmentTaskView}、
     *       {@code SkinReportView}、{@code SkinReportListItem}、{@code CareExecutionAdmission}、
     *       {@code CareExecutionRevalidation}、{@code CarePlanFullView}、{@code Progress}、
     *       {@code GimbalCurrentAssessmentView}、{@code ProgressWithSync}、{@code CareExecutionView}、
     *       {@code CareExecutionListItem}、{@code ControllerRef}、{@code ExecutionObservation}。</li>
     *   <li>{@code SmsChallengeData}→{@code SmsChallenge}：{@code AuthController.SmsChallengeData}（契约 M6）。</li>
     *   <li>{@code AppSessionData}→{@code AppSession}：{@code AuthController.AppSessionData}。</li>
     *   <li>{@code GimbalSessionData}→{@code GimbalSession}：{@code GimbalSessionController.GimbalSessionData}。</li>
     *   <li>{@code EchoJobAcceptedData}→{@code SystemEchoJobAccepted}：{@code SystemEchoController}。</li>
     *   <li>{@code EchoJobViewData}→{@code SystemEchoJobView}：{@code SystemEchoController}。</li>
     *   <li>{@code HeartbeatAck}→{@code GimbalHeartbeatAck}：{@code DeviceDtos.HeartbeatAck}（契约 M2-A02）。</li>
     *   <li>{@code StatusView}→{@code GimbalStatusView}：{@code DeviceDtos.StatusView}（契约 M2-A03）。</li>
     *   <li>{@code CapabilitiesView}→{@code MicrocrystalCapabilitiesView}：{@code DeviceDtos.CapabilitiesView}（契约 M2-A05）。</li>
     *   <li>{@code BindingResultView}→{@code GimbalBindingResult}：{@code DeviceDtos.BindingResultView}（契约 M2-A06）。</li>
     *   <li>{@code BindingStatusView}→{@code GimbalBindingStatusView}：{@code DeviceDtos.BindingStatusView}（契约 M2-A07）。</li>
     *   <li>{@code View}→{@code NotificationDestinationView}：{@code NotificationDestinationDtos.View}（契约 M5-A01）。</li>
     *   <li>{@code ObservationAckDto}→{@code ExecutionObservationAck}：{@code CareLedgerDtos.ObservationAckDto}（契约 M4-A05）。</li>
     *   <li>{@code ClosureResultDto}→{@code ExecutionClosureResult}：{@code CareLedgerDtos.ClosureResultDto}（契约 M4-A06）。</li>
     *   <li>{@code VerificationDto}→{@code Verification}：{@code CareAdmissionDtos.VerificationDto}（契约 components.Verification）。</li>
     *   <li>{@code AcknowledgedRecordDto}→{@code AcknowledgedRecord}：{@code CareLedgerDtos.AcknowledgedRecordDto}（契约 M4-A05）。</li>
     * </ul>
     */
    private static final Map<String, String> CONTRACT_RESPONSE_SCHEMA_ALIASES = Map.ofEntries(
            Map.entry("SmsChallengeData", "SmsChallenge"),
            Map.entry("AppSessionData", "AppSession"),
            Map.entry("GimbalSessionData", "GimbalSession"),
            Map.entry("EchoJobAcceptedData", "SystemEchoJobAccepted"),
            Map.entry("EchoJobViewData", "SystemEchoJobView"),
            Map.entry("HeartbeatAck", "GimbalHeartbeatAck"),
            Map.entry("StatusView", "GimbalStatusView"),
            Map.entry("CapabilitiesView", "MicrocrystalCapabilitiesView"),
            Map.entry("BindingResultView", "GimbalBindingResult"),
            Map.entry("BindingStatusView", "GimbalBindingStatusView"),
            Map.entry("View", "NotificationDestinationView"),
            Map.entry("ObservationAckDto", "ExecutionObservationAck"),
            Map.entry("ClosureResultDto", "ExecutionClosureResult"),
            Map.entry("VerificationDto", "Verification"),
            Map.entry("AcknowledgedRecordDto", "AcknowledgedRecord"));

    /**
     * 生成 component 名 → 契约 <strong>inline</strong> schema 的 <strong>JSON pointer</strong>。
     *
     * <p>这些结构在契约中<strong>只以内联（inline）形式出现，没有同名
     * {@code components.schemas} 定义</strong>，故既有 {@link #CONTRACT_RESPONSE_SCHEMA_ALIASES}
     * 按组件名对照会"跳过并打印"，Oracle 判定其"未与契约同等交叉校验"（三类重要嵌套响应缺少
     * required 承诺）。此处按 pointer 直接取契约 inline 节点的 {@code required} 做<strong>双向</strong>
     * 比对（少于=未修正、多于=invent，皆失败）。pointer 均已用 snakeyaml 实读
     * {@code backend/contracts/openapi/openapi.yaml} 复核（见各类 javadoc）。
     *
     * <ul>
     *   <li>{@code EchoJobLastError} → {@code /components/schemas/SystemEchoJobView/properties/lastError}
     *       （契约 {@code required=[reason, retryable]}、{@code additionalProperties=false}）。
     *       生成文档中它是命名 component（由 {@code lastError} 递归注册）。</li>
     *   <li>{@code SkinReportImage} → {@code /components/schemas/SkinReportView/properties/images/items}
     *       （契约 {@code required=[mediaId, contentUrl]}、{@code additionalProperties=false}）。</li>
     *   <li>{@code CurrentAssessment} →
     *       {@code /components/schemas/GimbalCurrentAssessmentView/properties/currentAssessment}
     *       （契约 {@code required=[taskId, status, photoVersion]}；{@code reportId} 不在 required 中）。</li>
     *   <li>{@code RecordWatermark} →
     *       {@code /components/schemas/CareExecutionView/properties/recordWatermark}
     *       （契约 {@code required} 缺省=空集、{@code additionalProperties=false}）⇒ 生成侧为空集时通过，
     *       不再进入"跳过"清单。</li>
     * </ul>
     */
    private static final Map<String, String> CONTRACT_INLINE_RESPONSE_POINTERS = Map.ofEntries(
            Map.entry("EchoJobLastError", "/components/schemas/SystemEchoJobView/properties/lastError"),
            Map.entry("SkinReportImage", "/components/schemas/SkinReportView/properties/images/items"),
            Map.entry("CurrentAssessment",
                    "/components/schemas/GimbalCurrentAssessmentView/properties/currentAssessment"),
            Map.entry("RecordWatermark",
                    "/components/schemas/CareExecutionView/properties/recordWatermark"));

    /**
     * 契约<strong>确实未定义</strong>任何对应响应投影结构的生成 component（核查结论，非"暂无映射"）。
     *
     * <p>{@code IncidentView}：按属性集（{@code incidentId}/{@code openedAt}/{@code lastReportedAt}）全量
     * 搜索契约，<strong>没有任何</strong> inline 节点含这些键；契约请求侧
     * {@code GimbalHeartbeatRequest.incidents}/{@code GimbalStatusView.incidents} 仅标
     * {@code x-detail: skeleton}、结构为 {@code {type:object, additionalProperties:true}}，未定义响应投影。
     * 故它确实<strong>无可比对对象</strong>：保留"跳过并披露"，但披露文案必须写明
     * <strong>契约未定义该结构</strong>，而非笼统的"无契约可比对"。Oracle 曾主张应与"空 required 集"
     * 比较，该主张与契约事实不符。</p>
     */
    private static final Map<String, String> CONTRACT_UNDEFINED_RESPONSE_SCHEMAS = Map.of(
            "IncidentView", "契约未定义该结构：请求侧 incidents 仅 x-detail: skeleton、"
                    + "结构为 {type:object, additionalProperties:true}，无任何含 incidentId/openedAt/"
                    + "lastReportedAt 的 inline 响应节点");

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

        // 6a) <strong>递归</strong>结构扫描：只扫描直接属性无法发现"展开字段内部的空 object /
        //     错误 items"（如 plan.steps 被建成 array<string>、incidents[].detail 空壳，而父字段
        //     已有 properties 被判 EXPANDED）。递归进入 properties/*、items、additionalProperties。
        problems.addAll(findStructureProblems(schemas));

        // 6a-2) 嵌套 required 落地证据（Oracle BLOCKER A 的精确复现点）：契约
        //       components.schemas.MissingRange.required=[from,to]，故真实文档的
        //       ErrorBody.details.missingRanges.items.required 必须为 [from,to]。此处断言的是
        //       /v3/api-docs 的<strong>序列化结果</strong>（Node 来自响应体 JSON），而非内存态。
        JsonNode missingRangeItems = schemas.path("ErrorBody").path("properties").path("details")
                .path("properties").path("missingRanges").path("items");
        if (!stringSet(missingRangeItems.path("required")).equals(Set.of("from", "to"))) {
            problems.add("嵌套 required 未落地：ErrorBody.details.missingRanges.items.required 应为"
                    + " [from,to]（契约 MissingRange），实际=" + missingRangeItems.path("required")
                    + "；节点=" + missingRangeItems);
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

    /**
     * <strong>递归</strong>结构门禁扫描（6a）：遍历每个 component schema 的每个属性，并递归进入
     * {@code properties.*}、{@code items}、{@code additionalProperties}（为 schema 时）。
     *
     * <ul>
     *   <li>任何 {@code type=object}（或无 {@code type} 但有 {@code properties}/{@code additionalProperties}）
     *       节点必须满足：有<strong>非空</strong> {@code properties}，或显式 {@code additionalProperties}
     *       （布尔或 schema），或属经核准的显式不透明声明（{@link ApiDocsApplier#OPAQUE_MARKER} 且
     *       路径在 {@link #APPROVED_OPAQUE_FIELDS} 内）；否则失败，消息含完整路径
     *       （如 {@code CarePlanFullView.plan.steps[]}）。</li>
     *   <li>任何 {@code type=array} 节点必须有 {@code items} 且 {@code items} 有 {@code type}
     *       或 {@code $ref}。</li>
     * </ul>
     *
     * <p>不试图从生成文档反推"本该是对象数组"——该约束由引擎在 {@code knownKeys} 裸
     * {@code array}/{@code object} 前缀处 fail fast（见 {@code ApiDocsApplier.keySchema}）。</p>
     */
    static List<String> findStructureProblems(JsonNode schemas) {
        List<String> problems = new ArrayList<>();
        if (schemas == null || !schemas.isObject()) {
            return problems;
        }
        for (java.util.Iterator<String> it = schemas.fieldNames(); it.hasNext(); ) {
            String name = it.next();
            scanStructure(schemas.path(name), name, problems);
        }
        return problems;
    }

    private static void scanStructure(JsonNode node, String path, List<String> problems) {
        if (node == null || !node.isObject()) {
            return;
        }
        if (node.has("$ref")) {
            return; // 被引用 schema 会在 components 遍历中单独扫描
        }
        String type = node.path("type").asText("");
        boolean hasProperties = node.path("properties").isObject() && node.path("properties").size() > 0;
        boolean hasAdditional = node.has("additionalProperties");
        boolean objectish = "object".equals(type)
                || (type.isEmpty() && (node.has("properties") || hasAdditional));
        // any 节点（无 type、无 $ref、无 properties、无 items、无 additionalProperties）必须受
        // APPROVED_ANY_PATHS 约束：否则可用它绕开"对象/数组结构必须显式声明"的递归门禁。
        // 注意：springdoc 对 record 派生的 47 个 component<strong>不带 type 键</strong>（只有
        // properties/required），这是 OpenAPI 3.1 的正常输出，故<strong>不能</strong>以"无 type"
        // 作为 any 的唯一判据；真正只带 description 的值节点才命中本判定。
        if (type.isEmpty() && !node.has("properties") && !node.has("items") && !hasAdditional
                && !APPROVED_ANY_PATHS.contains(path)) {
            problems.add("未核准的无 type 节点（any；只允许已核准的方案参数映射值）: " + path);
        }
        if (objectish) {
            boolean approvedOpaque = node.path("description").asText("")
                    .contains(ApiDocsApplier.OPAQUE_MARKER)
                    && APPROVED_OPAQUE_FIELDS.contains(path);
            if (!hasProperties && !hasAdditional && !approvedOpaque) {
                problems.add("嵌套空虚对象（无 properties 且无显式 additionalProperties）: " + path
                        + " = " + node);
            }
        }
        if ("array".equals(type)) {
            JsonNode items = node.path("items");
            if (!items.isObject() || (!items.has("type") && !items.has("$ref"))) {
                problems.add("数组缺少带 type/$ref 的 items: " + path + " = " + node);
            }
        }
        JsonNode properties = node.path("properties");
        if (properties.isObject()) {
            for (java.util.Iterator<String> it = properties.fieldNames(); it.hasNext(); ) {
                String prop = it.next();
                scanStructure(properties.path(prop), path + "." + prop, problems);
            }
        }
        if ("array".equals(type)) {
            scanStructure(node.path("items"), path + "[]", problems);
        }
        JsonNode additional = node.get("additionalProperties");
        if (additional != null && additional.isObject()) {
            scanStructure(additional, path + ".*", problems);
        }
    }

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
     * （生成名经 {@link #CONTRACT_REQUEST_SCHEMA_ALIASES} 映射）；（c）每个操作成功响应
     * {@code data} schema（含列表 {@code items} 条目类型，递归嵌套 {@code $ref}）的 {@code required}
     * 与契约 components 比对（生成名经 {@link #CONTRACT_RESPONSE_SCHEMA_ALIASES} 映射）。
     * 少于契约 → 失败（应经 {@code requiredProperties()} 修正）；多于契约 → 失败（不得 invent）。
     * 无契约对应者<strong>跳过并在输出中披露计数</strong>，不静默；（d）在契约中<strong>只有 inline
     * 定义</strong>的响应 component（{@link #CONTRACT_INLINE_RESPONSE_POINTERS}）按其 JSON pointer
     * 取 inline 节点的 {@code required} 做双向比对——此前这些结构被"跳过并打印"，不等同于与契约
     * 交叉校验。契约<strong>确实未定义</strong>对应结构者（{@link #CONTRACT_UNDEFINED_RESPONSE_SCHEMAS}）
     * 跳过并<strong>明确披露"契约未定义该结构"</strong>，不静默。
     */
    private static void crossCheckContractRequired(Map<String, JsonNode> generated, JsonNode schemas,
                                                   List<String> problems) throws Exception {
        Map<String, Object> contract = loadContract();
        Map<String, Set<String>> contractMultipart = contractMultipartRequired(contract);
        Map<String, Set<String>> contractSchemas = contractComponentRequired(contract);

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

        // (c) 成功响应 data schema required 集比对（含列表 items 条目类型，递归嵌套）。
        //     生成名经 CONTRACT_RESPONSE_SCHEMA_ALIASES 映射；少于契约 → 失败（应经 requiredProperties()
        //     修正）；多于契约 → 失败（不得 invent）。无契约对应者跳过并计数披露，不静默。
        List<String> skippedResponses = new ArrayList<>();
        List<String> undefinedInlineResponses = new ArrayList<>();
        for (String generatedName : responseSchemaNames(generated, schemas)) {
            // (d) 契约 inline schema：这些生成 component 在契约中只有 inline 定义（无同名
            //     components.schemas），按 JSON pointer 取 inline 节点 required 做双向比对，
            //     而不是"跳过并打印"了事。
            String inlinePointer = CONTRACT_INLINE_RESPONSE_POINTERS.get(generatedName);
            if (inlinePointer != null) {
                problems.addAll(crossCheckInlineRequired(generatedName, inlinePointer,
                        stringSet(schemas.path(generatedName).path("required")), contract));
                continue;
            }
            if (CONTRACT_UNDEFINED_RESPONSE_SCHEMAS.containsKey(generatedName)) {
                // 契约确实未定义该结构：保留跳过，但明确披露"契约未定义该结构"。
                undefinedInlineResponses.add(generatedName
                        + "（" + CONTRACT_UNDEFINED_RESPONSE_SCHEMAS.get(generatedName) + "）");
                continue;
            }
            String contractName = CONTRACT_RESPONSE_SCHEMA_ALIASES.getOrDefault(generatedName, generatedName);
            if (!contractSchemas.containsKey(contractName)) {
                skippedResponses.add(generatedName + "→" + contractName);
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
                problems.add("响应 data schema required 多于契约（不得 invent 必填性）: "
                        + generatedName + "→" + contractName + " extra=" + extra
                        + " generated=" + actual + " contract=" + expected);
            } else {
                problems.add("响应 data schema required 少于契约（应经 requiredProperties() 修正）: "
                        + generatedName + "→" + contractName + " missing=" + missing
                        + " generated=" + actual + " contract=" + expected);
            }
        }
        if (!skippedResponses.isEmpty()) {
            System.out.println("[coverage-gate] 无契约可比对、已跳过并披露的响应 data schema:"
                    + " responseSchemas=" + skippedResponses);
        }
        if (!undefinedInlineResponses.isEmpty()) {
            System.out.println("[coverage-gate] 契约未定义对应结构、已跳过并披露的响应 component"
                    + "（披露口径：契约未定义该结构，而非笼统'无契约可比对'）:"
                    + " undefined=" + undefinedInlineResponses);
        }
    }

    /**
     * 契约 inline 响应 schema 的 required 双向交叉校验（section d）。
     *
     * <p>按 JSON pointer 取契约中 inline 节点的 {@code required}（缺省视为空集），与生成 component
     * 的 {@code required} 比对：少于契约 = 未修正；多于契约 = invent；两者皆失败。pointer 无法解析
     * 或节点非对象时也报告（防止映射表陈旧而静默通过）。</p>
     *
     * <p>本方法为 {@code static} 且只依赖入参，供门禁与<strong>单元负向测试</strong>共用——
     * 测试可构造合成契约根证明"少于契约"确实被捕获（见 {@code ApiDocsApplierTest}）。</p>
     */
    static List<String> crossCheckInlineRequired(String generatedName, String pointer,
                                                 Set<String> generatedRequired,
                                                 Map<String, Object> contractRoot) {
        List<String> problems = new ArrayList<>();
        Object node = resolvePointer(contractRoot, pointer);
        if (!(node instanceof Map<?, ?> nodeMap)) {
            problems.add("契约 inline pointer 无法解析（映射表可能陈旧）: "
                    + generatedName + " → " + pointer);
            return problems;
        }
        Set<String> expected = new LinkedHashSet<>();
        Object req = nodeMap.get("required");
        if (req instanceof List<?> list) {
            list.forEach(r -> expected.add(String.valueOf(r)));
        }
        if (generatedRequired.equals(expected)) {
            return problems;
        }
        Set<String> missing = new LinkedHashSet<>(expected);
        missing.removeAll(generatedRequired);
        Set<String> extra = new LinkedHashSet<>(generatedRequired);
        extra.removeAll(expected);
        if (!extra.isEmpty()) {
            problems.add("inline 响应 schema required 多于契约（不得 invent 必填性）: "
                    + generatedName + " → " + pointer + " extra=" + extra
                    + " generated=" + generatedRequired + " contract=" + expected);
        } else {
            problems.add("inline 响应 schema required 少于契约（应经 requiredProperties() 修正）: "
                    + generatedName + " → " + pointer + " missing=" + missing
                    + " generated=" + generatedRequired + " contract=" + expected);
        }
        return problems;
    }

    /**
     * 解析 RFC6901 JSON pointer（如 {@code /components/schemas/X/properties/y}）到 snakeyaml 加载的
     * 契约对象；任一段缺失返回 {@code null}。支持 {@code ~1}→{@code /}、{@code ~0}→{@code ~} 转义。
     */
    static Object resolvePointer(Map<String, Object> root, String pointer) {
        if (root == null || pointer == null) {
            return null;
        }
        Object node = root;
        String[] parts = pointer.split("/", -1);
        for (int i = 1; i < parts.length; i++) {
            if (!(node instanceof Map<?, ?> map)) {
                return null;
            }
            String key = parts[i].replace("~1", "/").replace("~0", "~");
            node = map.get(key);
            if (node == null) {
                return null;
            }
        }
        return node;
    }

    /**
     * 生成文档中全部成功响应 {@code data} 相关 schema 名：对每个 2xx JSON 响应取信封的
     * {@code data} schema（列表响应为内联 {@code {items, nextCursor}}，故进入其 {@code items}
     * 的 {@code $ref}），再递归进入 components 的嵌套 {@code $ref}。
     * <p>只从 {@code data} 子树出发，不把 {@code meta}/{@code requestId} 计入响应 data 比对。</p>
     */
    private static Set<String> responseSchemaNames(Map<String, JsonNode> generated, JsonNode schemas) {
        Set<String> out = new LinkedHashSet<>();
        java.util.Deque<String> queue = new java.util.ArrayDeque<>();
        for (JsonNode op : generated.values()) {
            JsonNode responses = op.path("responses");
            for (java.util.Iterator<String> it = responses.fieldNames(); it.hasNext(); ) {
                String code = it.next();
                if (!(code.length() == 3 && code.charAt(0) == '2')) {
                    continue;
                }
                JsonNode schema = responses.path(code).path("content")
                        .path("application/json").path("schema");
                JsonNode data = schema.path("properties").path("data");
                collectSchemaRefs(data, out, queue);
            }
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
    private static Map<String, Set<String>> contractMultipartRequired(Map<String, Object> contract) {
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
    private static Map<String, Set<String>> contractComponentRequired(Map<String, Object> contract) {
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

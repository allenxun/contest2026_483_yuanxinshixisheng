package cn.yuanxin.mvp.web.docs.catalog;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * <strong>共享信封</strong>的联调文档目录（统一成功/错误信封与 {@code meta}）。
 *
 * <p>这些 schema 被<strong>全部</strong>端点引用，若交给四个业务域目录分别登记会产生
 * {@code duplicatePropertyDocs} 冲突，故由 orchestrator 单点提供（四条业务域目录被明令
 * <em>不得</em>为 {@code SuccessEnvelope}/{@code ErrorEnvelope}/{@code ErrorBody}/{@code Meta}/
 * {@code ListData}/{@code JsonNode} 写 propertyDocs）。</p>
 *
 * <p>注意：{@code SuccessEnvelope} 与 {@code ListData} 在生成文档中<strong>已被引擎修剪</strong>
 * （每个操作的成功响应都改为内联的"信封 + 类型化 data"，列表响应改为内联
 * {@code {items, nextCursor}}），因此这里<strong>不</strong>为它们登记 propertyDocs——
 * 为不存在的 schema 登记会触发 {@code unknownPropertySchemas} fail fast。
 * 实测保留在 {@code components.schemas} 中的共享类型只有 {@code Meta}、{@code ErrorEnvelope}、
 * {@code ErrorBody}（以及被两个不透明字段引用的空壳 {@code JsonNode}）。</p>
 *
 * <p>本目录<strong>不声明任何操作</strong>（{@link #entries()} 为空、{@link #tags()} 为空），
 * 只提供属性级与自由结构文档。</p>
 */
@Component
@Profile({"dev", "test"})
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class CommonEnvelopeApiDocs implements ApiDocsCatalog {

    /**
     * {@code error.code} 的全部合法取值 = {@code web/error/ErrorCode.java} 的 29 个常量。
     * 逐码语义/触发条件/客户端动作见 {@link ErrorCodeDocs}（生成文档的错误响应描述即取自它）。
     */
    private static final List<String> ERROR_CODES = List.of(
            "INVALID_INPUT", "UPLOAD_TOO_LARGE", "UNSUPPORTED_IMAGE", "FACE_QUALITY_REJECTED",
            "AUTH_REQUIRED", "SESSION_INVALID",
            "RESOURCE_NOT_VISIBLE", "CALLER_NOT_ALLOWED", "FACE_NOT_VERIFIED", "GRANT_REVOKED",
            "IDEMPOTENCY_CONTENT_CONFLICT", "BINDING_CHANGED", "TASK_REPLACED",
            "PHOTO_VERSION_CONFLICT", "DEVICE_OCCUPIED", "PLAN_NOT_READY", "PLAN_COMPLETED",
            "EXECUTION_NOT_RESUMABLE", "RECORD_CONFLICT", "CLOSURE_GAPS", "STOP_NOT_CONFIRMED",
            "BOUND_TO_OTHER", "REQUEST_IN_PROGRESS",
            "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "DEPENDENCY_TIMEOUT",
            "INTERNAL", "UNSUPPORTED_CONTRACT", "NOT_IMPLEMENTED");

    @Override
    public String domain() {
        return "common-envelope";
    }

    @Override
    public List<io.swagger.v3.oas.models.tags.Tag> tags() {
        // 本目录不声明操作，故不引入新标签（标签由各业务域目录提供）。
        return List.of();
    }

    @Override
    public Map<String, ApiDocEntry> entries() {
        // 共享信封不对应任何单一操作。
        return Map.of();
    }

    @Override
    public Map<String, Map<String, PropertyDoc>> propertyDocs() {
        return Map.of(
                "Meta", Map.of(
                        "replayed", new PropertyDoc(
                                "本次响应是否为<strong>幂等重放</strong>：携带 Idempotency-Key 且"
                                        + "同主体、同操作、同键、同内容（payload_hash 按 RFC 8785 JCS + SHA-256 计算）"
                                        + "命中既有成功/拒绝记录时为 true，表示返回的是原结果而非新建效果。"
                                        + "首次处理为 false。客户端不应把重放响应当作新的副作用。",
                                null, null, "false", null),
                        "serverTime", new PropertyDoc(
                                "服务端时间，RFC 3339 UTC、秒精度（服务端 Instant 截断到秒），无时区偏移。"
                                        + "用于与设备本地时钟对照；<strong>客户端时钟不作为全局排序依据</strong>，"
                                        + "涉及顺序判断请使用服务端返回的代次/序号（如 statusRevision、"
                                        + "observationEpoch+observationSeq、sourceSeq）。",
                                null, null, "2026-09-13T08:30:00Z", "date-time")),
                "ErrorEnvelope", Map.of(
                        "requestId", new PropertyDoc(
                                "本次 HTTP 尝试的请求 ID（UUID），与响应头 X-Request-Id 同值；"
                                        + "每个响应（含错误与 204）都携带。<strong>每次重试都会变化</strong>，"
                                        + "不能用作幂等键；报障时请附该值。",
                                null, null, "0e6a2b1c-4d5e-6f70-8a9b-0c1d2e3f4a5b", null),
                        "error", new PropertyDoc(
                                "错误主体（见 ErrorBody）。客户端<strong>应以 error.code 做分支判断</strong>，"
                                        + "不要解析 message 文本（message 供人读，可能调整）。",
                                null, null, null, null)),
                "ErrorBody", Map.of(
                        "code", new PropertyDoc(
                                "稳定的业务原因码（封闭枚举，共 29 个），是客户端分支判断的<strong>唯一依据</strong>。"
                                        + "HTTP 状态与 retryable 由该码决定：400 INVALID_INPUT；"
                                        + "401 AUTH_REQUIRED/SESSION_INVALID；"
                                        + "403 CALLER_NOT_ALLOWED/FACE_NOT_VERIFIED/GRANT_REVOKED；"
                                        + "404 RESOURCE_NOT_VISIBLE；"
                                        + "409 冲突族（IDEMPOTENCY_CONTENT_CONFLICT/BINDING_CHANGED/TASK_REPLACED/"
                                        + "PHOTO_VERSION_CONFLICT/DEVICE_OCCUPIED/PLAN_NOT_READY/PLAN_COMPLETED/"
                                        + "EXECUTION_NOT_RESUMABLE/RECORD_CONFLICT/CLOSURE_GAPS/STOP_NOT_CONFIRMED/"
                                        + "BOUND_TO_OTHER/REQUEST_IN_PROGRESS）；413 UPLOAD_TOO_LARGE；"
                                        + "415 UNSUPPORTED_IMAGE；422 FACE_QUALITY_REJECTED/UNSUPPORTED_CONTRACT；"
                                        + "429 RATE_LIMITED；500 INTERNAL；501 NOT_IMPLEMENTED；"
                                        + "503 DEPENDENCY_UNAVAILABLE；504 DEPENDENCY_TIMEOUT。"
                                        + "逐码触发条件与客户端动作见各端点的错误响应描述。"
                                        + "注意：测肤任务的 failureCode 字段是<strong>另一套独立的封闭枚举</strong>"
                                        + "（AssessmentTaskView.failureCode，含 PROVIDER_CONTRACT_VIOLATION）；"
                                        + "该码<strong>刻意</strong>不属于本 HTTP error.code 枚举：它由 Worker 写入"
                                        + "skin_assessments.failure_code，经 assessments/FailureProjection 公开白名单"
                                        + "（共 9 码）投影后由 M3-A03 外发，retryable 对所有非 null 取值恒为 false。"
                                        + "因此在 HTTP 错误码枚举中找不到它是正常的，应以任务 failureCode 字段"
                                        + "（契约 AssessmentTaskView.failureCode 的 enum）为准。",
                                null, ERROR_CODES, "INVALID_INPUT", null),
                        "message", new PropertyDoc(
                                "供人阅读的简述，<strong>不保证稳定、不得用于程序分支</strong>；"
                                        + "不含内部诊断（堆栈、SQL、内部列名等绝不外发）。",
                                null, null, "request validation failed", null),
                        "retryable", new PropertyDoc(
                                "是否可按原逻辑重试。仅 4 个码为 true：REQUEST_IN_PROGRESS（按 Retry-After 等待后用"
                                        + "<strong>同一</strong>幂等键重试）、RATE_LIMITED、DEPENDENCY_UNAVAILABLE、"
                                        + "DEPENDENCY_TIMEOUT（受限退避重试）；其余一律 false——重试无意义，"
                                        + "需修正输入或刷新状态后<strong>换新键</strong>再试。"
                                        + "依赖类失败<strong>绝不</strong>等价于“核验通过”。",
                                null, null, "false", null),
                        "details", new PropertyDoc(
                                "可选的结构化补充信息，<strong>只含调用方可见的冲突字段/缺失序号等</strong>，"
                                        + "键集合随 code 而定（见本字段的已知键与可扩展边界说明）；"
                                        + "不出现时表示无补充信息。绝不包含内部诊断内容。",
                                null, null, null, null)));
    }

    /**
     * {@code ErrorBody.details} 内部<strong>嵌套</strong>键的递归结构。
     *
     * <p>两个键的真实元素是<strong>对象</strong>而非字符串，若沿用一层 DSL 会被生成为
     * {@code array<string>}，从而与真实响应冲突并误导代码生成器：</p>
     * <ul>
     *   <li>{@code fields}：{@code List.of(Map.of("field", …, "reason", …))}
     *       （取证 {@code MemberAccessGrantController.java:209}）；注意部分生产者只给
     *       {@code field} 而无 {@code reason}（如 {@code CareBigints.java:50}），故为开放对象。</li>
     *   <li>{@code missingRanges}：契约 {@code components.schemas.MissingRange} =
     *       {@code {from, to}}，两键均 <strong>required</strong>、{@code additionalProperties: false}
     *       ⇒ 封闭对象；两值均为无符号 bigint 十进制字符串。</li>
     * </ul>
     */
    @Override
    public Map<String, Map<String, KnownKeyDoc>> structuredKeys() {
        return Map.of(
                "ErrorBody.details", Map.of(
                        "fields", KnownKeyDoc.array(
                                KnownKeyDoc.openObject(
                                        Map.of(
                                                "field", KnownKeyDoc.str(
                                                        "违规字段名（JSON 字段名，camelCase）"),
                                                "reason", KnownKeyDoc.str(
                                                        "违规原因概述；部分生产者只给 field 而不给 reason，"
                                                                + "客户端不得假设其存在")),
                                        "单个字段违规项；元素为对象而非字符串"),
                                "array，逐字段违规原因（code=INVALID_INPUT 且由 @Valid 校验触发时出现）"),
                        "missingRanges", KnownKeyDoc.array(
                                // 契约 components.schemas.MissingRange：required=[from,to]、
                                // additionalProperties=false ⇒ 嵌套层也必须声明 required，
                                // 否则机器契约比权威契约更宽松，代码生成器会允许客户端漏填。
                                KnownKeyDoc.closedObject(
                                        Map.of(
                                                "from", KnownKeyDoc.str(
                                                        "缺口区间起点序号（含），无符号 bigint 十进制字符串",
                                                        "12"),
                                                "to", KnownKeyDoc.str(
                                                        "缺口区间终点序号（含），无符号 bigint 十进制字符串",
                                                        "17")),
                                        List.of("from", "to"),
                                        "单个记录缺口区间（契约 MissingRange：from/to 均必填、封闭，"
                                                + "不生成与巨大 W 成比例的数组）"),
                                "array，收尾时缺失的记录序号区间（code=CLOSURE_GAPS 时出现；"
                                        + "受输出上限约束，配合 more 判断是否被截断）")));
    }

    @Override
    public Map<String, FreeFormDoc> freeFormDocs() {
        return Map.of(
                "ErrorBody.details", new FreeFormDoc(
                        "错误补充信息（Map）。键集合<strong>随 error.code 而定</strong>，且只包含调用方可见的信息："
                                + "校验类给出违规字段，冲突类给出当前代次或缺失区间，限流/处理中给出等待秒数。"
                                + "内部诊断列（如 failure_detail、last_error 的原始内容、堆栈、SQL、内部列名）"
                                + "<strong>绝不外发</strong>；异步任务失败只投影封闭的 reason 枚举与 retryable。",
                        // 12 个已知键 > Map.of 的 10 对上限，故用 Map.ofEntries。
                        Map.ofEntries(
                                Map.entry("fields",
                                        "array，参数校验失败的逐字段原因，元素为 {field, reason}"
                                                + "（code=INVALID_INPUT 且由 @Valid 校验触发时出现）"),
                                Map.entry("reason",
                                        "string，概述性原因标识（如 invalid_cursor 表示游标非法；"
                                                + "EXECUTION_NOT_RESUMABLE 时为封闭枚举 admitted_not_paused / "
                                                + "unknown_needs_fresh_paused_observation / stopped_not_resumable / "
                                                + "closed_not_resumable / running_not_paused / plan_completed / "
                                                + "verification_revision_mismatch；PLAN_NOT_READY、STOP_NOT_CONFIRMED "
                                                + "亦用本键）"),
                                Map.entry("retryAfterSeconds",
                                        "integer，建议等待秒数（code=REQUEST_IN_PROGRESS，"
                                                + "与响应头 Retry-After 同时给出）"),
                                Map.entry("currentBindingRevision",
                                        "string，当前绑定代次（无符号 bigint 十进制字符串）；"
                                                + "code=BINDING_CHANGED 且发生于云台绑定/解绑时出现，只含当前代次，"
                                                + "不泄漏其他账号信息"),
                                Map.entry("currentDestinationRevision",
                                        "string，当前通知目标代次（无符号 bigint 十进制字符串）；"
                                                + "code=BINDING_CHANGED 且发生于通知目标登记时出现"),
                                Map.entry("conflictingRecordIds",
                                        "array<string>，冲突的实际完成记录 ID（最多 20 个）；"
                                                + "code=RECORD_CONFLICT 时出现"),
                                Map.entry("totalConflicts",
                                        "integer，冲突总数（可能大于已列出的 conflictingRecordIds 数量）"),
                                Map.entry("missingRanges",
                                        "array，收尾时缺失的记录序号区间；code=CLOSURE_GAPS 时出现"),
                                Map.entry("more",
                                        "boolean，missingRanges 是否被截断（true 表示还有更多区间未列出）"),
                                Map.entry("finalCount",
                                        "integer，服务端已确认的实际完成记录总数；code=CLOSURE_GAPS 时出现"),
                                Map.entry("totalCount",
                                        "integer，承诺范围 1..W 内的记录总量；code=CLOSURE_GAPS 时出现"),
                                Map.entry("apiId",
                                        "string，未实现端点的 API 标识（code=NOT_IMPLEMENTED 时出现，"
                                                + "可能还含 plannedPackage）")),
                        true,
                        "开放扩展：客户端<strong>必须容忍 details 出现未来新增键</strong>，"
                                + "不得因未知键而失败（契约对 501 NOT_IMPLEMENTED 的响应亦明确要求容忍未来字段）。"
                                + "反向不成立：上表已知键并非在任何错误中都会出现，缺失即表示不适用，"
                                + "客户端不得假设其存在。各键的具体出现条件以 error.code 为准。",
                        "{\"fields\":[{\"field\":\"photoVersion\",\"reason\":\"must follow the current version\"}]}"));
    }
}

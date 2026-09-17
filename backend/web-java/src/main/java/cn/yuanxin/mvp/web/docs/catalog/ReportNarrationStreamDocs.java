package cn.yuanxin.mvp.web.docs.catalog;

import cn.yuanxin.mvp.web.config.NonProductionCondition;
import cn.yuanxin.mvp.web.error.ErrorCode;
import io.swagger.v3.oas.models.tags.Tag;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Conditional;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * 测肤报告文案播报域联调文档目录：
 * {@code GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream}（响应为 SSE）。
 *
 * <p>本端点是<b>用户授权的增量</b>：从 T05 {@code report_payload} 读取三项评分并真实转发给
 * 已部署的 llm-rag-api 报告评估 SSE（{@code POST
 * /internal/v1/weijing/reports/assess:stream}）。它<b>不在</b>
 * {@code backend/contracts/openapi/openapi.yaml} 的既有操作集中，故 <b>catalog-only</b>：
 * 仅登记于本目录，不写入契约（也正因此，覆盖率门禁对该无契约操作跳过错误码集交叉校验）。</p>
 *
 * <p><b>限制声明（必须如实展示）</b>：当前 Worker 写入的 {@code report_payload} 只有
 * {@code schema_version}/{@code conclusion}/{@code metrics}/{@code description}/{@code images}/
 * {@code model_info} 六个键，<b>不含</b> {@code pores}/{@code spots}/{@code surface_gloss}
 * ⇒ 真实报告会在发 AI 前以 422 {@code UNSUPPORTED_CONTRACT} fail-closed，端到端尚未打通；
 * 另有两处口径（{@code score=null} 的可接受性、regions 左右/区域码是否需要转换）待真实 AI 实测确认。</p>
 *
 * <p>本类只写文档内容，不触碰任何控制器/DTO/业务代码。</p>
 */
@Component
@Conditional(NonProductionCondition.class)
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class ReportNarrationStreamDocs implements ApiDocsCatalog {

    /** 测肤报告播报。 */
    private static final String TAG_REPORT_NARRATION = "测肤报告播报";

    @Override
    public String domain() {
        return "report-narration";
    }

    @Override
    public List<Tag> tags() {
        return List.of(new Tag().name(TAG_REPORT_NARRATION)
                .description("测肤报告文案播报流（用户授权增量）：云台按任务触发服务端真实转发 llm-rag-api 的"
                        + "报告评估 SSE，并以 SSE 逐事件回传；不支持重放。"));
    }

    @Override
    public Map<String, ApiDocEntry> entries() {
        return Map.of(
                "GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream",
                new ApiDocEntry(
                        TAG_REPORT_NARRATION,
                        "测肤报告文案播报流（SSE）",
                        """
                        用途：云台在报告就绪后按任务触发服务端读取 T05 持久化的三项评分，真实转发给
                        llm-rag-api 的报告评估 SSE，并以 SSE 逐事件回传播报文案（仅 delta，不转发 AI 完整事件）。
                        调用方主体：仅云台设备会话（Authorization: Bearer <gimbal device session token>）；
                        APP 会话主体一律 403 CALLER_NOT_ALLOWED 且不产生任何下游请求；未认证请求由
                        BearerAuthFilter 统一 401（AUTH_REQUIRED/SESSION_INVALID）。
                        前置与顺序（预流检查在请求线程按序完成，任一失败在建立 SSE 前返回统一 JSON 错误信封）：
                        ① 仅云台主体；② taskId 必须对该云台可见（非本云台任务 → 404 RESOURCE_NOT_VISIBLE；
                        已非该云台当前任务 → 409 TASK_REPLACED）；③ 任务报告必须已就绪（reportId 非空），否则
                        404 RESOURCE_NOT_VISIBLE；④ T05 report_payload 必须含 pores/spots/surface_gloss 三个
                        JSON 对象且各组通过评分结构校验，否则 422 UNSUPPORTED_CONTRACT（fail-closed，绝不回退
                        替身/合成文案、绝不把 metrics 伪映射成三项）；⑤ 下游连接失败/预流非 2xx → 503
                        DEPENDENCY_UNAVAILABLE，预流超时 → 504 DEPENDENCY_TIMEOUT。
                        成功响应：200，Content-Type: text/event-stream、Cache-Control: no-store。
                        事件映射与 seq 纪律：下游 response.accepted → start、response.delta → text_delta、
                        response.completed → done、response.failed → error；服务端逐事件即时 flush（绝不缓冲整段
                        文案），seq 从 1 起每事件严格 +1（start=1，其后每个 text_delta 与唯一终态逐个 +1）。
                        data 为 JSON，含 requestId/taskId/reportId/seq；text_delta 另含 delta；done 只带安全元数据
                        （不带完整 spoken_text/plan/指标/任何评估结果）；error 含 code 与固定安全 message。
                        成功流恰一个终态；零 delta 却收到 completed 视为失败（error 终态），累计 delta 与
                        completed.spoken_text 不一致只记服务端告警、仍正常发 done。
                        下游契约（服务端内部）：POST {app.report-narration.base-url}/internal/v1/weijing/reports/
                        assess:stream，Header X-Service-Name=medical-platform、X-API-Key、X-Request-Id（每次调用
                        新生成）、Idempotency-Key（每次调用全新，不发送 Last-Event-ID、绝不断点续传）、
                        X-Protocol-Version=1.0、traceparent（W3C）、Accept: text/event-stream、
                        Content-Type: application/json；body 恰好 {"pores":{...},"spots":{...},
                        "surface_gloss":{...}}，每组只含白名单四键 score/severity/name/regions，不发送图片、
                        成员资料、完整 report_payload、metrics 或其它 trace；绝不转发云台的 Authorization/Cookie。
                        幂等语义（重要限制）：本端点无本地幂等存储，每次调用都使用全新的下游 Idempotency-Key
                        ——客户端重试会产生一次新评估（下游亦无重放存储），不支持重放。
                        配置与降级：app.report-narration.base-url / api-key 缺省为空（安全占位），真实值由部署
                        环境注入；app.providers.mode=disabled 或未配置（非生产）时一律预流 503
                        DEPENDENCY_UNAVAILABLE，绝不回退替身或合成文案；生产信号下缺配置拒绝启动。
                        错误处理：CALLER_NOT_ALLOWED 换用云台会话；RESOURCE_NOT_VISIBLE 换任务或等待报告就绪；
                        TASK_REPLACED 以当前任务为准；UNSUPPORTED_CONTRACT（422）表示持久化载荷不符合三项评分
                        契约（当前 Worker 报告即属此类，端到端尚未打通），非重试类；DEPENDENCY_UNAVAILABLE（503）
                        与 DEPENDENCY_TIMEOUT（504）为下游依赖失败/超时（预流为 HTTP 问题，流内为 error 事件），
                        受限重试（注意"重试即新评估"语义）。
                        限制声明（必须如实展示）：不支持 Last-Event-ID、断点续传、重放或取消 API；客户端断开时
                        服务端取消下游 AI 连接。当前 Worker 的 report_payload 不含三项评分，真实报告会在发 AI 前
                        422 fail-closed，端到端尚未打通；score=null 的可接受性与 regions 左右/区域码口径两处
                        待真实 AI 实测确认，本实现不做任何语义转换。本接口为 catalog-only（按用户授权增量，
                        不入 backend/contracts/openapi/openapi.yaml）。
                        """,
                        List.of(new ApiDocEntry.ParamDoc("taskId", "path",
                                "必填，path，UUID 字符串（T05.id），测肤任务引用；必须仍是该云台的当前任务"
                                        + "且报告已就绪，其持久化 report_payload 须含三项评分对象。",
                                "7f3c2b1a-9d4e-4c5f-8a6b-1d2e3f4a5b6c", null)),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.binary("200",
                                "SSE 事件流（Content-Type: text/event-stream、Cache-Control: no-store）。"
                                        + "事件序列 start → text_delta ×N → done（或恰一个 error 终态），"
                                        + "每事件即时 flush；data 含 requestId/taskId/reportId/seq"
                                        + "（text_delta 另含 delta）；预流失败改以 JSON 错误信封表达",
                                "text/event-stream")),
                        List.of(ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.TASK_REPLACED, ErrorCode.UNSUPPORTED_CONTRACT,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT)));
    }

    @Override
    public Map<String, Map<String, PropertyDoc>> propertyDocs() {
        return Map.of();
    }

    @Override
    public Map<String, FreeFormDoc> freeFormDocs() {
        return Map.of();
    }
}

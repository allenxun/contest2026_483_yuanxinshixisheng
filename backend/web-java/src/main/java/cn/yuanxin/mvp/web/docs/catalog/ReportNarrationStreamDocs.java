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
 * MOCK 测肤报告文案播报域联调文档目录：
 * {@code GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream}（响应为 SSE）。
 *
 * <p><b>本接口为 MOCK 联调增量</b>：返回由固定联调数据生成的报告播报文案，
 * <b>非</b>正式算法/RAG/AI 结果，不调用算法/RAG/AI、不读取密钥。它是<b>用户授权的增量</b>，
 * 不在 {@code backend/contracts/openapi/openapi.yaml} 的既有操作集中，
 * 故 <b>catalog-only</b>：仅登记于本目录，不写入契约（也正因此，覆盖率门禁对该无契约操作
 * 跳过错误码集交叉校验）。</p>
 *
 * <p>本类只写文档内容，不触碰任何控制器/DTO/业务代码。</p>
 */
@Component
@Conditional(NonProductionCondition.class)
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class ReportNarrationStreamDocs implements ApiDocsCatalog {

    /** MOCK 测肤报告文案播报。 */
    private static final String TAG_REPORT_NARRATION = "测肤报告播报（MOCK）";

    @Override
    public String domain() {
        return "report-narration";
    }

    @Override
    public List<Tag> tags() {
        return List.of(new Tag().name(TAG_REPORT_NARRATION)
                .description("MOCK 测肤报告文案播报流（联调增量）：返回由固定联调数据生成的报告播报文案，"
                        + "以 SSE 逐事件下发；非正式算法/RAG/AI 结果。"));
    }

    @Override
    public Map<String, ApiDocEntry> entries() {
        return Map.of(
                "GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream",
                new ApiDocEntry(
                        TAG_REPORT_NARRATION,
                        "测肤报告文案播报流（MOCK）",
                        """
                        本接口为 MOCK 联调增量——返回固定联调数据生成的报告播报文案，非正式算法/RAG/AI 结果；
                        不调用算法/RAG/AI，不读取密钥，无持久化、无重放。
                        用途：云台在报告就绪后按任务读取一段固定播报文案（联调客户端联调 SSE 消费与渲染）。
                        调用方主体：仅云台设备会话（Authorization: Bearer <gimbal device session token>）；
                        APP 会话主体一律 403 CALLER_NOT_ALLOWED；未认证请求由 BearerAuthFilter 统一 401
                        （AUTH_REQUIRED/SESSION_INVALID）。
                        前置与顺序（预流检查在请求线程按序完成，任一失败在建立 SSE 前返回统一 JSON 错误信封）：
                        ① 仅云台主体；② 仅非生产环境提供 MOCK 生成器，生产缺省 → 503 DEPENDENCY_UNAVAILABLE；
                        ③ taskId 必须对该云台可见（非本云台任务 → 404 RESOURCE_NOT_VISIBLE；已非该云台当前
                        任务 → 409 TASK_REPLACED）；④ 任务报告必须已就绪（reportId 非空），否则
                        404 RESOURCE_NOT_VISIBLE。
                        成功响应：200，Content-Type: text/event-stream、Cache-Control: no-store。
                        事件顺序固定：start → text_delta → text_delta → done；每事件即时 flush（绝不缓冲整段文案）。
                        data 为 JSON，含 requestId/taskId/reportId/seq（seq 从 1 起、每事件严格 +1）；
                        text_delta 事件另含 delta（本 MOCK 恰好两段 delta，拼接后为完整播报文案）。
                        done 为成功终态；仅当流内出现意外错误时，在 done 之前写出恰好一个 error 终态
                        （data 含 code=INTERNAL_ERROR 与固定安全 message，不含异常细节/堆栈）。
                        限制声明（必须如实展示）：不支持 Last-Event-ID、断点续传、重放或取消 API；
                        客户端断开时服务端静默结束本次发送。本接口为 catalog-only（按用户授权增量，
                        不入 backend/contracts/openapi/openapi.yaml）。
                        错误处理：CALLER_NOT_ALLOWED 换用云台会话；RESOURCE_NOT_VISIBLE 换任务或等待报告就绪；
                        TASK_REPLACED 以当前任务为准；DEPENDENCY_UNAVAILABLE 为生产环境未提供 MOCK 生成器。
                        """,
                        List.of(new ApiDocEntry.ParamDoc("taskId", "path",
                                "必填，path，UUID 字符串（T05.id），测肤任务引用；必须仍是该云台的当前任务"
                                        + "且报告已就绪。",
                                "7f3c2b1a-9d4e-4c5f-8a6b-1d2e3f4a5b6c", null)),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.binary("200",
                                "SSE 事件流（Content-Type: text/event-stream、Cache-Control: no-store）。"
                                        + "事件顺序固定 start → text_delta → text_delta → done，每事件即时 flush；"
                                        + "data 含 requestId/taskId/reportId/seq（text_delta 另含 delta）；"
                                        + "done 为成功终态，流内意外错误时以恰一个 error 终态替代",
                                "text/event-stream")),
                        List.of(ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.TASK_REPLACED, ErrorCode.DEPENDENCY_UNAVAILABLE)));
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
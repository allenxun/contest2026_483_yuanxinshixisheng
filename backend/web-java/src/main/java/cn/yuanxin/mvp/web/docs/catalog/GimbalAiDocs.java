package cn.yuanxin.mvp.web.docs.catalog;

import cn.yuanxin.mvp.web.config.NonProductionCondition;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.gimbalai.dto.GimbalAiMessageRequest;
import io.swagger.v3.oas.models.tags.Tag;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Conditional;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * 云台 AI 文本透传域联调文档目录：{@code POST /api/v1/gimbal-ai/messages}（响应为 SSE）。
 *
 * <p>本端点是<b>用户授权的增量</b>，权威来源为本轮任务书（增量契约）与
 * {@code .mvp-d-runtime/} 中 AI 服务 {@code /internal/v1/ai/responses:stream} 的只读实证；
 * 它<b>不在</b> {@code backend/contracts/openapi/openapi.yaml} 的既有操作集中，
 * 故无契约 {@code x-error-codes} 可对照（覆盖率门禁对无契约操作跳过码集交叉校验）。</p>
 *
 * <p><b>限制声明（必须如实展示）</b>：本端点为<b>无状态、无上下文</b>的文本问答——
 * 不存储也不回传 {@code continuation_state}，因此<b>不能</b>承载真实的测肤后续追问；
 * 真正的报告后追问需要先存储并在请求中回传评估的 {@code continuation_state}，
 * 属后续增量（本轮明确禁止）。</p>
 *
 * <p>本类只写文档内容，不触碰任何控制器/DTO/业务代码。</p>
 */
@Component
@Conditional(NonProductionCondition.class)
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class GimbalAiDocs implements ApiDocsCatalog {

    /** 云台 AI 文本透传。 */
    private static final String TAG_GIMBAL_AI = "云台AI问答";

    @Override
    public String domain() {
        return "gimbal-ai";
    }

    @Override
    public List<Tag> tags() {
        return List.of(new Tag().name(TAG_GIMBAL_AI)
                .description("云台 AI 文本透传（用户授权增量）：云台提交一段文本，服务端流式转发给"
                        + " AI 服务的 /internal/v1/ai/responses:stream，并以 SSE 逐事件回传。当前为"
                        + " 无状态、无上下文问答，不具备测肤后续追问能力。"));
    }

    @Override
    public Map<String, ApiDocEntry> entries() {
        return Map.of(
                "POST /api/v1/gimbal-ai/messages", new ApiDocEntry(
                        TAG_GIMBAL_AI,
                        "云台 AI 文本问答（流式，无状态透传）",
                        """
                        用途：云台设备提交一段用户文本，服务端<b>流式</b>转发给 AI 服务并逐事件回传。
                        调用方：仅云台设备会话（Authorization: Bearer <gimbal device session token>）。
                        APP 会话主体一律 403 CALLER_NOT_ALLOWED，且不产生任何下游请求；未认证请求由
                        BearerAuthFilter 统一 401（AUTH_REQUIRED/SESSION_INVALID）。
                        请求（严格形状）：body 仅允许 text 一个字段（1—2000 字符，去空白后非空）；
                        未知字段、空/超长 → 400 INVALID_INPUT，解析失败发生在任何下游调用之前。
                        成功响应：200，Content-Type: text/event-stream（Cache-Control: no-store）。
                        服务端逐事件、每事件即时 flush（绝不缓冲整段答案），外部事件为：
                        - response.accepted（信息性）；
                        - response.delta：data 为 {"delta":"…"}，按序即时下发；
                        - response.completed：data 为 {"answerText":"…"}（权威答案），恰一个成功终态；
                        - response.failed：data 为 {"code":"DEPENDENCY_UNAVAILABLE|DEPENDENCY_TIMEOUT",
                          "message":"…"}（仅安全码/文案，不含堆栈、下游响应体、continuation_state 或密钥），
                          恰一个失败终态。
                        服务端对下游 SSE 做<b>解析-校验-重编码白名单</b>，绝不字节透传：只认
                        response.accepted/response.delta/response.completed/response.failed；未知事件、重复/缺失终态、畸形、
                        EOF、读取超时一律 fail-closed（流内失败转成一个 response.failed 终态）。客户端断开时
                        服务端取消下游连接。
                        错误映射：<b>预流失败</b>（授权、校验、下游连接失败/预流非 2xx/预流超时）
                        在建立 SSE 前发生，返回统一 JSON 错误信封与 HTTP 状态（如 400/403/503/504）；
                        一旦流已开始，失败只能以一个 response.failed 事件表达（HTTP 仍为 200）。
                        下游契约（服务端内部）：POST {app.gimbal-ai.base-url}/internal/v1/ai/responses:stream，
                        Header X-Service-Name=medical-platform、X-API-Key、X-Request-Id（服务端每次调用
                        新生成，与 body.request_id 一致）、Idempotency-Key（每次调用全新，且不发送
                        Last-Event-ID、绝不断点续传）、X-Protocol-Version=1.0、traceparent（W3C）、
                        Accept: text/event-stream、Content-Type: application/json；body 为
                        {protocol_version:"1.0", request_id, use_case:"APP_AGENT_CONVERSATION",
                        input:{text}}，不含 continuation_state。绝不回退一次性接口。
                        幂等语义（重要限制）：本端点无本地幂等存储，每次调用都使用全新的下游
                        Idempotency-Key——客户端重试会产生一个<b>新问题</b>（下游亦无重放存储）。
                        配置与降级：app.gimbal-ai.base-url / api-key 缺省为空（安全占位），真实值由部署
                        环境注入；app.providers.mode=disabled 或未配置（非生产）时一律预流 503
                        DEPENDENCY_UNAVAILABLE，绝不回退替身或合成答案；生产信号下缺配置拒绝启动。
                        错误处理：INVALID_INPUT 修正 body；CALLER_NOT_ALLOWED 换用云台会话；
                        DEPENDENCY_UNAVAILABLE（503）与 DEPENDENCY_TIMEOUT（504）为下游依赖失败/超时
                        （预流为 HTTP 问题，流内为 response.failed 事件），受限重试（注意"重试即新问题"语义）。
                        **能力限制（如实披露）**：这是无状态、无上下文的文本问答，不存储也不回传
                        continuation_state，因此无法承载真实的测肤报告后续追问；真正的报告后追问需要
                        先存储并回传评估的 continuation_state，属后续增量（本轮明确不在范围内）。
                        """,
                        List.of(),
                        List.of(),
                        GimbalAiMessageRequest.class,
                        "请求体：仅 text（必填，1—2000 字符，去空白后非空）；未知字段一律 400 INVALID_INPUT。",
                        List.of(ApiDocEntry.SuccessDoc.binary("200",
                                "SSE 事件流（text/event-stream）：response.accepted / response.delta{delta} / "
                                        + "response.completed{answerText} / response.failed{code,message}；每事件即时 flush，"
                                        + "恰一个终态；预流失败改以 JSON 错误信封表达",
                                "text/event-stream")),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT)));
    }

    @Override
    public Map<String, Map<String, PropertyDoc>> propertyDocs() {
        return Map.ofEntries(
                Map.entry("GimbalAiMessageRequest", Map.of(
                        "text", PropertyDoc.of(
                                "必填，字符串，用户文本，1—2000 字符（去空白后非空）；服务端仅原样转发给"
                                        + " AI 服务，不落地存储（无会话历史）。",
                                "帮我看看今天的护肤建议"))));
    }

    @Override
    public Map<String, FreeFormDoc> freeFormDocs() {
        return Map.of();
    }
}

package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.error.ApiException;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.util.UUID;

/**
 * 测肤报告播报 SSE 端点（真实转发下游报告评估 SSE）。
 *
 * <p>{@code GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream}：
 * Bearer 认证 → 仅云台主体（APP → 403 CALLER_NOT_ALLOWED）。预流检查与下游开流在请求线程按序
 * 完成（{@link ReportNarrationService#openStream}）：主体校验、既有任务可见性
 * （{@link cn.yuanxin.mvp.web.assessments.AssessmentReadService#getTask} 内部产出 404/409）、
 * 报告就绪（reportId 为空 → 404）、T05 {@code report_payload} 三项结构校验
 * （缺/非法 → 422 UNSUPPORTED_CONTRACT）、下游预流失败（503/504）。任一失败在返回 SSE 之前
 * 抛 {@link ApiException}，由 {@link ReportNarrationStreamErrorAdvice} 映射为真实 HTTP 状态的
 * JSON 错误信封（即使客户端带 {@code Accept: text/event-stream}）。</p>
 *
 * <p>预流成功后才建立 {@code text/event-stream}（{@code Cache-Control: no-store}），逐事件
 * 即时 flush：{@code start → text_delta ×N → done}，{@code seq} 从 1 起严格 +1；流内失败以
 * 恰好一个 {@code error} 终态表达（HTTP 仍 200）。客户端断开（写/flush IOException）时
 * {@code finally} 关闭下游 AI 连接。不支持 Last-Event-ID、断点续传、重放或取消 API。</p>
 */
@RestController
@Validated
public class ReportNarrationStreamController {

    /** 流内失败终态的固定安全文案（绝不携带异常细节/堆栈）。 */
    static final String ERROR_MESSAGE = "报告播报生成失败";

    private final ReportNarrationService service;

    public ReportNarrationStreamController(ReportNarrationService service) {
        this.service = service;
    }

    @GetMapping(value = "/api/v1/skin-assessment-tasks/{taskId}/report-narration-stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<StreamingResponseBody> reportNarrationStream(
            @PathVariable UUID taskId,
            PrincipalContext principal) {
        // 预流检查 + 开下游（请求线程，任一失败 → 统一 JSON 错误信封，绝不进入 SSE）。
        ReportNarrationService.Session session = service.openStream(principal, taskId);
        StreamingResponseBody stream = output -> {
            try {
                service.pump(session, output);
            } finally {
                // 正常完成或客户端断开：始终取消/关闭下游 AI 连接。
                session.close();
            }
        };
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noStore())
                .body(stream);
    }
}

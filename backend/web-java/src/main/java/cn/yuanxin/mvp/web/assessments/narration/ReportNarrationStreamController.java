package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.assessments.AssessmentReadService;
import cn.yuanxin.mvp.web.assessments.dto.AssessmentTaskView;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * MOCK 测肤报告文案播报 SSE 端点（联调增量，catalog-only）。
 *
 * <p>{@code GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream}：
 * Bearer 认证 → 仅云台主体（APP → 403 CALLER_NOT_ALLOWED）。预流检查在请求线程按序
 * 完成——主体校验、MOCK 生成器可用性（生产 fail-closed 503）、任务可见性
 * （{@link AssessmentReadService#getTask} 内部产出 404/409）、报告就绪
 * （reportId 为空 → 404）。任一失败在返回 SSE 之前抛 {@link ApiException}，
 * 由统一异常处理映射为 JSON 错误信封与真实 HTTP 状态。</p>
 *
 * <p>预流成功后才建立 {@code text/event-stream}（{@code Cache-Control: no-store}），
 * 逐事件即时 flush，事件序列固定为 {@code start → text_delta ×2 → done}，
 * {@code seq} 从 1 起严格 +1。仅当流内出现意外 {@link RuntimeException} 时，
 * 在 {@code done} 之前写出恰好一个 {@code error} 终态（仅安全固定字段）。
 * 客户端断开（写/flush IOException）静默结束本次发送。不支持 Last-Event-ID、
 * 断点续传、重放或取消 API。</p>
 */
@RestController
@Validated
public class ReportNarrationStreamController {

    /** 流内失败终态的固定安全文案（绝不携带异常细节/堆栈）。 */
    static final String ERROR_MESSAGE = "报告播报生成失败";

    private final AssessmentReadService readService;
    private final ObjectProvider<MockReportNarrationGenerator> generatorProvider;
    private final ObjectMapper objectMapper;

    public ReportNarrationStreamController(
            AssessmentReadService readService,
            ObjectProvider<MockReportNarrationGenerator> generatorProvider,
            ObjectMapper objectMapper) {
        this.readService = readService;
        this.generatorProvider = generatorProvider;
        this.objectMapper = objectMapper;
    }

    @GetMapping(value = "/api/v1/skin-assessment-tasks/{taskId}/report-narration-stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<StreamingResponseBody> reportNarrationStream(
            @PathVariable UUID taskId,
            PrincipalContext principal) {
        // 预流检查（请求线程，任一失败 → 统一 JSON 错误信封，绝不进入 SSE）。
        if (principal.principalType() != PrincipalType.GIMBAL) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "only a gimbal may stream the skin report narration");
        }
        MockReportNarrationGenerator generator = generatorProvider.getIfAvailable();
        if (generator == null) {
            // 生产环境 MOCK 生成器缺席：fail-closed。
            throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "report narration mock is unavailable in this environment");
        }
        AssessmentTaskView view = readService.getTask(taskId, principal);
        if (view.reportId() == null) {
            // 报告未就绪：与报告投影同口径的不可见语义。
            throw new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE,
                    "report not ready; narration is not available");
        }

        String requestId = principal.requestId();
        String reportId = view.reportId();
        List<String> chunks = generator.deltaChunks();
        StreamingResponseBody stream = output ->
                writeNarration(output, requestId, taskId, reportId, chunks);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noStore())
                .body(stream);
    }

    /**
     * 逐事件写出并 flush。终态纪律：{@code done} 与 {@code error} 恰有其一；
     * 客户端断开或流内异常后，本方法不再写出任何后续事件。
     */
    private void writeNarration(OutputStream out, String requestId, UUID taskId,
                                String reportId, List<String> chunks) {
        int seq = 1;
        try {
            writeEvent(out, "start", json(payload(requestId, taskId, reportId, seq, null)));
            for (String chunk : chunks) {
                seq++;
                writeEvent(out, "text_delta",
                        json(payload(requestId, taskId, reportId, seq, chunk)));
            }
            seq++;
            writeEvent(out, "done", json(payload(requestId, taskId, reportId, seq, null)));
        } catch (IOException clientDisconnect) {
            // 客户端断开：静默结束本次发送（无终态、无重放/续传）。
        } catch (RuntimeException failure) {
            // 流内意外失败：尽力写出恰好一个 error 终态（仅安全固定字段）。
            try {
                writeEvent(out, "error", json(errorPayload(requestId, taskId, reportId, seq + 1)));
            } catch (Exception ignored) {
                // 客户端已断开或写入失败：无更多可做，绝不泄露异常细节。
            }
        }
    }

    /** start/text_delta/done 的 data 载荷（键序 requestId、taskId、reportId、seq[、delta]）。 */
    private static Map<String, Object> payload(String requestId, UUID taskId, String reportId,
                                               int seq, String delta) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("requestId", requestId);
        data.put("taskId", taskId.toString());
        data.put("reportId", reportId);
        data.put("seq", seq);
        if (delta != null) {
            data.put("delta", delta);
        }
        return data;
    }

    /** error 终态的 data 载荷（键序 requestId、taskId、reportId、seq、code、message）。 */
    private static Map<String, Object> errorPayload(String requestId, UUID taskId, String reportId,
                                                    int seq) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("requestId", requestId);
        data.put("taskId", taskId.toString());
        data.put("reportId", reportId);
        data.put("seq", seq);
        data.put("code", "INTERNAL_ERROR");
        data.put("message", ERROR_MESSAGE);
        return data;
    }

    private void writeEvent(OutputStream out, String event, String jsonData) throws IOException {
        out.write(("event: " + event + "\ndata: " + jsonData + "\n\n")
                .getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception encoding) {
            throw new IllegalStateException("failed to encode SSE event payload");
        }
    }
}
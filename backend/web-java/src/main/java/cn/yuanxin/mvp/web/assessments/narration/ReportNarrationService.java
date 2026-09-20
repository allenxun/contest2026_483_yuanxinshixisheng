package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.assessments.AssessmentReadService;
import cn.yuanxin.mvp.web.assessments.AssessmentRepository;
import cn.yuanxin.mvp.web.assessments.dto.AssessmentTaskView;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * 报告播报业务入口：门禁 → 读 T05 {@code report_payload} → 校验 → 开下游流 → {@code pump}。
 *
 * <p><b>预流顺序</b>（请求线程，任一失败在建立 SSE 之前抛 {@link ApiException}，
 * 由 {@link ReportNarrationStreamErrorAdvice} 渲染为 JSON 错误信封）：</p>
 * <ol>
 *   <li>仅 {@link PrincipalType#GIMBAL}；APP 主体在<b>打开下游之前</b>拒绝（403 CALLER_NOT_ALLOWED）；</li>
 *   <li>复用 {@link AssessmentReadService#getTask} 既有门禁（404 {@code RESOURCE_NOT_VISIBLE} /
 *       409 {@code TASK_REPLACED}）——<b>不复制、不重写</b>门禁逻辑；</li>
 *   <li>报告未就绪（{@code reportId} 为空）→ 404 {@code RESOURCE_NOT_VISIBLE}；</li>
 *   <li>读 {@code report_payload}：<b>只读复用</b> {@link AssessmentRepository#findByReportId}
 *       （该仓唯一暴露 {@code report_payload::text} 的既有方法），<b>不修改</b>共享读路径。
 *       <b>注意</b>：冻结规格 §4.1 第 4 步写作 {@code findById(taskId)} 取
 *       {@code ViewRow.reportPayload()}，但当前 {@link AssessmentRepository.ViewRow} <b>不含</b>
 *       {@code reportPayload} 字段（{@code findById} 也不查询 {@code report_payload}），而规格同时
 *       禁止修改 {@link AssessmentRepository}。两者冲突时以"不得改共享读路径"为准，改用既有的
 *       {@code findByReportId(reportId)} → {@code ReportRow.reportPayload()}（规格同句给出的行号
 *       {@code AssessmentRepository:84,91} 正指向该方法）。此为第二次查询，为不改共享读路径而接受；</li>
 *   <li><b>report_ready 门禁复核</b>：{@code row.status()} 必须仍为 {@code report_ready} 且
 *       {@code row.id()} 必须等于 {@code taskId}，否则 404 {@code RESOURCE_NOT_VISIBLE}
 *       （与 {@code SkinReportService:110-112} 同口径；两次查询之间任务可能已转入补拍）；</li>
 *   <li>payload 为空/空白 → 404 {@code RESOURCE_NOT_VISIBLE}；</li>
 *   <li>校验三项结构（{@link ReportNarrationScoreExtractor}）：缺/非法 → 422
 *       {@code UNSUPPORTED_CONTRACT}（fail-closed，绝不用 {@code metrics} 伪映射、绝不回退 mock、
 *       绝不发空 body）；</li>
 *   <li>开下游：预流失败 → 503 {@code DEPENDENCY_UNAVAILABLE} / 504 {@code DEPENDENCY_TIMEOUT}。</li>
 * </ol>
 *
 * <p><b>流内</b>（HTTP 已 200）：{@code MALFORMED}/{@code UNAVAILABLE} →
 * {@code DEPENDENCY_UNAVAILABLE}；{@code TIMEOUT} → {@code DEPENDENCY_TIMEOUT}；下游
 * {@code response.failed} 的 code 含 {@code TIMEOUT} → {@code DEPENDENCY_TIMEOUT}，否则
 * {@code DEPENDENCY_UNAVAILABLE}。循环正常结束却无终态 → 防御性写一个 {@code error}；
 * 意外 {@code RuntimeException} → 尽力写一个 {@code error}（写失败则忽略）。客户端断开
 * （写/flush {@code IOException}）→ <b>不写</b> error 终态，直接上抛，由控制器 finally 关闭下游。</p>
 *
 * <p><b>幂等语义</b>：每次调用生成全新的下游 {@code Idempotency-Key}，重试即新评估；
 * 无本地幂等存储、不支持重放。</p>
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiService} 同源范式、刻意不共享。</p>
 */
@Service
public class ReportNarrationService {

    private static final Logger log = LoggerFactory.getLogger(ReportNarrationService.class);

    /** 预流依赖失败的固定安全文案（不泄露下游诊断）。 */
    static final String DEPENDENCY_MESSAGE = "report narration dependency failure; no narration available";

    private final AssessmentReadService readService;
    private final AssessmentRepository assessmentRepository;
    private final ReportNarrationClient client;
    private final ObjectMapper objectMapper;

    public ReportNarrationService(AssessmentReadService readService,
                                  AssessmentRepository assessmentRepository,
                                  ReportNarrationClient client,
                                  ObjectMapper objectMapper) {
        this.readService = readService;
        this.assessmentRepository = assessmentRepository;
        this.client = client;
        this.objectMapper = objectMapper;
    }

    /** 一次播报会话：下游流句柄 + 外部帧所需的固定元数据。 */
    public record Session(ReportNarrationStream stream, String requestId, String taskId, String reportId)
            implements AutoCloseable {

        @Override
        public void close() {
            stream.close();
        }
    }

    /**
     * 鉴权 + 读 payload + 校验 + 打开下游流。预流失败会抛异常（由 advice 映射为 JSON problem）。
     */
    public Session openStream(PrincipalContext principal, UUID taskId) {
        if (principal.principalType() != PrincipalType.GIMBAL) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "only a gimbal may stream the skin report narration");
        }
        AssessmentTaskView view = readService.getTask(taskId, principal);
        if (view.reportId() == null) {
            throw notReady();
        }
        String reportId = view.reportId();
        AssessmentRepository.ReportRow row = assessmentRepository
                .findByReportId(UUID.fromString(reportId))
                .orElseThrow(ReportNarrationService::notReady);
        // report_ready 门禁（任务书明令保留）+ 归属复核。与 SkinReportService:110-112 同口径：
        // getTask 与 findByReportId 是两次独立查询，其间 Worker 可能把任务转入补拍并改写
        // status/report_id，故必须在此重新确认"这一行仍是 report_ready"，否则会把一份已被
        // 取代的报告送给 AI。uq_assessment_report UNIQUE(report_id)（V1:198）保证 report_id
        // 全局唯一，所以显式的 id==taskId 复核是纵深防御（防将来 schema 变化），不是唯一保障。
        if (!"report_ready".equals(row.status()) || !taskId.equals(row.id())) {
            throw notReady();
        }
        String payload = row.reportPayload();
        if (payload == null || payload.isBlank()) {
            throw notReady();
        }

        ReportNarrationScores scores;
        try {
            scores = ReportNarrationScoreExtractor.extract(payload);
        } catch (ApiException invalid) {
            if (invalid.getCode() == ErrorCode.UNSUPPORTED_CONTRACT) {
                // 只记 taskId、失败类别与键路径清单；绝不含 payload 内容、评分值、成员资料、密钥。
                log.warn("report narration payload rejected taskId={} details={}",
                        taskId, invalid.getDetails());
            }
            throw invalid;
        }

        ReportNarrationStream downstream;
        try {
            downstream = client.openStream(scores);
        } catch (ReportNarrationException failure) {
            // 预流失败：建立 SSE 之前发生 → 统一 JSON problem（HTTP 映射），不是流内 error 事件。
            ErrorCode code = failure.kind() == ReportNarrationFailureKind.TIMEOUT
                    ? ErrorCode.DEPENDENCY_TIMEOUT
                    : ErrorCode.DEPENDENCY_UNAVAILABLE;
            log.warn("report narration pre-stream failure taskId={} kind={} downstreamStatus={} downstreamCode={}",
                    taskId, failure.kind(), failure.httpStatus(),
                    failure.safeCode() == null ? "<none>" : failure.safeCode());
            throw new ApiException(code, DEPENDENCY_MESSAGE);
        }
        return new Session(downstream, principal.requestId(), taskId.toString(), reportId);
    }

    /**
     * 消费下游事件并逐事件重编码为外部 SSE 写到 {@code out}。
     *
     * <p><b>seq 纪律（无特例）</b>：{@code seq} 恒等于"已写出的外部帧数 + 1"，即
     * <b>每一次 writeEvent/writeError 之前立即自增</b>，对 {@code start}/{@code text_delta}/
     * {@code done}/{@code error} 一律同一规则。正常流可见结果 = {@code start}(1) →
     * {@code text_delta}(2..N+1) → {@code done}(N+2)；异常路径（例如下游首个事件就失败）从 0 起
     * 自增，故唯一一个 {@code error} 帧拿到 {@code seq=1}。</p>
     *
     * <p>外部事件序列：成功时 {@code start} → {@code text_delta}×N → {@code done}；失败则以恰一个
     * {@code error} 终态替代。每事件即时 flush，绝不缓冲整段文案。客户端断开（写 IOException）时
     * 不写 error 终态，直接上抛。</p>
     */
    public void pump(Session session, OutputStream out) throws IOException {
        int seq = 0;
        try {
            ReportNarrationEvent event;
            while ((event = session.stream().next()) != null) {
                switch (event.type()) {
                    case ACCEPTED -> {
                        seq++;
                        writeEvent(out, "start", json(payload(session, seq, null)));
                    }
                    case DELTA -> {
                        seq++;
                        writeEvent(out, "text_delta", json(payload(session, seq, event.delta())));
                    }
                    case COMPLETED -> {
                        seq++;
                        writeEvent(out, "done", json(payload(session, seq, null)));
                        return;
                    }
                    case FAILED -> {
                        seq++;
                        writeError(out, session, seq, codeForFailedEvent(event.failedCode()));
                        return;
                    }
                }
            }
            // 解析器保证终态；防御性兜底：仍按失败终态处理（绝不静默成功）。
            seq++;
            writeError(out, session, seq, ErrorCode.DEPENDENCY_UNAVAILABLE);
        } catch (ReportNarrationException failure) {
            ErrorCode code = failure.kind() == ReportNarrationFailureKind.TIMEOUT
                    ? ErrorCode.DEPENDENCY_TIMEOUT
                    : ErrorCode.DEPENDENCY_UNAVAILABLE;
            // 只记 taskId/分类/状态/下游码；绝不记评分值、区域值、spoken_text 或 SSE 原文。
            log.warn("report narration stream failure taskId={} kind={} downstreamStatus={} downstreamCode={}",
                    session.taskId(), failure.kind(), failure.httpStatus(),
                    failure.safeCode() == null ? "<none>" : failure.safeCode());
            seq++;
            writeError(out, session, seq, code);
        } catch (RuntimeException unexpected) {
            // 意外失败：尽力写一个 error 终态；写失败则忽略（绝不泄漏异常细节）。
            log.warn("report narration unexpected stream failure taskId={} exception={}",
                    session.taskId(), unexpected.getClass().getSimpleName());
            try {
                seq++;
                writeError(out, session, seq, ErrorCode.INTERNAL);
            } catch (IOException ignored) {
                // 客户端已断开或写入失败：无更多可做。
            }
        }
    }

    private static ErrorCode codeForFailedEvent(String downstreamCode) {
        if (downstreamCode != null && downstreamCode.toUpperCase().contains("TIMEOUT")) {
            return ErrorCode.DEPENDENCY_TIMEOUT;
        }
        return ErrorCode.DEPENDENCY_UNAVAILABLE;
    }

    private void writeError(OutputStream out, Session session, int seq, ErrorCode code) throws IOException {
        Map<String, Object> data = payload(session, seq, null);
        data.put("code", code.name());
        data.put("message", ReportNarrationStreamController.ERROR_MESSAGE);
        writeEvent(out, "error", json(data));
    }

    /** start/text_delta/done 的 data 载荷（键序 requestId、taskId、reportId、seq[、delta]）。 */
    private static Map<String, Object> payload(Session session, int seq, String delta) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("requestId", session.requestId());
        data.put("taskId", session.taskId());
        data.put("reportId", session.reportId());
        data.put("seq", seq);
        if (delta != null) {
            data.put("delta", delta);
        }
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

    private static ApiException notReady() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE,
                "report not ready; narration is not available");
    }
}

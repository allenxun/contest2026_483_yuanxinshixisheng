package cn.yuanxin.mvp.web.gimbalai;

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

/**
 * 云台 AI 文本透传业务入口（无状态、无副作用、无本地幂等存储）。
 *
 * <p>仅 {@link PrincipalType#GIMBAL} 可调用；APP 主体在<b>打开下游之前</b>拒绝
 * （403 CALLER_NOT_ALLOWED），绝无下游请求。</p>
 *
 * <p><b>预流失败</b>（授权、下游连接/预流非 2xx/预流超时）以 {@link ApiException}
 * 上抛 → 统一 JSON problem 映射；<b>流内失败</b>（畸形 SSE、缺终态、EOF、读超时）
 * 转成<b>恰好一个</b>外部 {@code response.failed} 终态事件（安全 code/message）。</p>
 *
 * <p><b>逐事件解析-校验-重编码</b>（白名单），绝不做字节透传：外部只发
 * {@code response.accepted}/{@code response.delta}/{@code response.completed}/
 * {@code response.failed}；每事件后 {@code flush()}，绝不缓冲整段答案。</p>
 */
@Service
public class GimbalAiService {

    private static final Logger log = LoggerFactory.getLogger(GimbalAiService.class);

    /** 对客户端统一的最小依赖失败文案（不泄露下游诊断）。 */
    static final String DEPENDENCY_MESSAGE = "gimbal AI dependency failure; no answer available";

    private final GimbalAiClient client;
    private final ObjectMapper objectMapper;

    public GimbalAiService(GimbalAiClient client, ObjectMapper objectMapper) {
        this.client = client;
        this.objectMapper = objectMapper;
    }

    /**
     * 鉴权 + 打开下游流。预流失败会抛异常（由 MVC advice 映射为 JSON problem）。
     */
    public GimbalAiStream openStream(PrincipalContext principal, String text) {
        if (principal.principalType() != PrincipalType.GIMBAL) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "only a gimbal may use the AI text passthrough");
        }
        try {
            return client.openStream(text);
        } catch (GimbalAiException failure) {
            // 预流失败：建立 SSE 之前发生 → 统一 JSON problem（HTTP 映射），不是流内 response.failed 事件。
            ErrorCode code = failure.kind() == GimbalAiFailureKind.TIMEOUT
                    ? ErrorCode.DEPENDENCY_TIMEOUT
                    : ErrorCode.DEPENDENCY_UNAVAILABLE;
            log.warn("gimbal AI pre-stream failure kind={} downstreamStatus={} downstreamCode={}",
                    failure.kind(), failure.httpStatus(),
                    failure.safeCode() == null ? "<none>" : failure.safeCode());
            throw new ApiException(code, DEPENDENCY_MESSAGE);
        }
    }

    /**
     * 消费下游事件并逐事件重编码为外部 SSE 写到 {@code out}。
     *
     * <p>恰一个终态：{@code response.completed} 或 {@code response.failed}。客户端断开（写 IOException）
     * 时不写 response.failed，直接上抛，由调用方在 finally 关闭下游流（取消下游）。</p>
     */
    public void pump(GimbalAiStream stream, OutputStream out) throws IOException {
        try {
            GimbalAiEvent event;
            while ((event = stream.next()) != null) {
                switch (event.type()) {
                    case ACCEPTED -> writeEvent(out, "response.accepted", json(Map.of()));
                    case DELTA -> writeEvent(out, "response.delta", json(Map.of("delta", event.delta())));
                    case COMPLETED -> {
                        writeEvent(out, "response.completed",
                                json(Map.of("answerText", event.answerText())));
                        return;
                    }
                    case FAILED -> {
                        writeFailed(out, codeForFailedEvent(event.failedCode()));
                        return;
                    }
                }
            }
            // 解析器保证终态；防御性兜底：仍按失败终态处理（绝不静默成功）。
            writeFailed(out, ErrorCode.DEPENDENCY_UNAVAILABLE);
        } catch (GimbalAiException failure) {
            ErrorCode code = failure.kind() == GimbalAiFailureKind.TIMEOUT
                    ? ErrorCode.DEPENDENCY_TIMEOUT
                    : ErrorCode.DEPENDENCY_UNAVAILABLE;
            // 只记分类/状态/下游码；绝不记用户文本、密钥或 SSE 原文（requestId 由 MDC 携带）。
            log.warn("gimbal AI stream failure kind={} downstreamStatus={} downstreamCode={}",
                    failure.kind(), failure.httpStatus(),
                    failure.safeCode() == null ? "<none>" : failure.safeCode());
            writeFailed(out, code);
        }
    }

    private static ErrorCode codeForFailedEvent(String downstreamCode) {
        if (downstreamCode != null && downstreamCode.toUpperCase().contains("TIMEOUT")) {
            return ErrorCode.DEPENDENCY_TIMEOUT;
        }
        return ErrorCode.DEPENDENCY_UNAVAILABLE;
    }

    private void writeFailed(OutputStream out, ErrorCode code) throws IOException {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("code", code.name());
        data.put("message", DEPENDENCY_MESSAGE);
        writeEvent(out, "response.failed", json(data));
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

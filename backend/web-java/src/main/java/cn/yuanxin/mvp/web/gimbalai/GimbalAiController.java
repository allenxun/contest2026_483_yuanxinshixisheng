package cn.yuanxin.mvp.web.gimbalai;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.gimbalai.dto.GimbalAiMessageRequest;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/**
 * 云台 AI 文本透传 HTTP 端点（无状态、无上下文；响应为 SSE）。
 *
 * <p>POST /api/v1/gimbal-ai/messages：Bearer 认证（BearerAuthFilter）→ 仅云台主体
 * （APP → 403 CALLER_NOT_ALLOWED）。<b>预流失败</b>（授权、校验、下游连接/预流非 2xx/
 * 预流超时）在返回前抛异常 → 统一 JSON problem；<b>成功预流</b>后以
 * {@code Content-Type: text/event-stream} 逐事件推送
 * {@code response.accepted}/{@code response.delta}/{@code response.completed}/
 * {@code response.failed}（每事件 flush，绝不缓冲整段答案），
 * 流内失败转成恰好一个 {@code response.failed} 终态。</p>
 */
@RestController
@Validated
@RequestMapping("/api/v1/gimbal-ai")
public class GimbalAiController {

    private final GimbalAiService service;

    public GimbalAiController(GimbalAiService service) {
        this.service = service;
    }

    @PostMapping("/messages")
    public ResponseEntity<StreamingResponseBody> messages(
            @Valid @RequestBody GimbalAiMessageRequest body,
            PrincipalContext principal) {
        // 预流失败（含 APP 403、下游预流失败）在此抛出 → advice 返回 JSON problem。
        GimbalAiStream downstream = service.openStream(principal, body.text());
        StreamingResponseBody stream = output -> {
            try {
                service.pump(downstream, output);
            } finally {
                // 正常完成或客户端断开：始终取消/关闭下游连接。
                downstream.close();
            }
        };
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noStore())
                .body(stream);
    }
}

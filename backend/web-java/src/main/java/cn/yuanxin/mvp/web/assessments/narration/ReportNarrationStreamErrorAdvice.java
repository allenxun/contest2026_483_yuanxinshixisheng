package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.ErrorEnvelope;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

/**
 * 播报流端点的<strong>预流错误</strong>渲染器（仅作用于
 * {@link ReportNarrationStreamController}）。
 *
 * <p><b>为什么需要本类</b>：{@code report-narration-stream} 以
 * {@code produces=text/event-stream} 声明且真实 SSE 客户端发送
 * {@code Accept: text/event-stream}。预流失败抛 {@link ApiException} 时，
 * 全局 {@code GlobalExceptionHandler} 返回 JSON 信封但<strong>未预设
 * Content-Type</strong>，Spring MVC 会退回到内容协商：可生产类型仅
 * {@code text/event-stream}，与请求 {@code Accept} 无法匹配 → 以
 * {@code HttpMediaTypeNotAcceptableException} 收敛为 500，丢失真实错误状态。</p>
 *
 * <p>本 advice 仅对上述控制器生效，返回与全局处理器<strong>完全相同</strong>的
 * {@link ErrorEnvelope} 信封，并<strong>显式预设</strong> {@code Content-Type:
 * application/json}（Spring MVC 对预设 Content-Type 跳过协商），从而在
 * {@code Accept: text/event-stream} 下也如实返回 403/404/409/503 等预流错误。
 * 不修改任何既有异常处理路径，不影响其它控制器。</p>
 */
@RestControllerAdvice(assignableTypes = ReportNarrationStreamController.class)
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ReportNarrationStreamErrorAdvice {

    private final EnvelopeSupport envelopes;
    private final ObjectMapper objectMapper;

    public ReportNarrationStreamErrorAdvice(EnvelopeSupport envelopes, ObjectMapper objectMapper) {
        this.envelopes = envelopes;
        this.objectMapper = objectMapper;
    }

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, Object>> apiException(ApiException ex, HttpServletRequest request) {
        ErrorEnvelope body = envelopes.error(request,
                new ErrorEnvelope.ErrorBody(ex.getCode().name(), ex.getMessage(),
                        ex.isRetryable(), ex.getDetails()));
        Map<String, Object> map = objectMapper.convertValue(body, Map.class);
        HttpHeaders headers = new HttpHeaders();
        ex.getHeaders().forEach(headers::set);
        return ResponseEntity.status(ex.getHttpStatus())
                .contentType(MediaType.APPLICATION_JSON)
                .headers(headers)
                .body(map);
    }
}
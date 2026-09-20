package cn.yuanxin.mvp.web.sms;

import com.aliyun.dysmsapi20170525.models.SendSmsRequest;
import com.aliyun.dysmsapi20170525.models.SendSmsResponseBody;
import com.aliyun.tea.TeaException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.net.SocketTimeoutException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * {@link AliyunSmsSendGateway} 响应映射单元测试（注入假 {@code SmsCaller}，<b>不</b>联网、
 * <b>不</b>发真实短信）。重点锁定：仅 {@code Code=="OK"} 为受理成功；其它 Code/异常/
 * 缺失字段一律失败并分类。使用明显假凭据。
 */
class AliyunSmsSendGatewayTest {

    private static final String FAKE_PHONE = "+8610000000000";
    private static final String FAKE_CODE = "246810";

    private static AliyunSmsProperties fakeProperties() {
        return new AliyunSmsProperties("dysmsapi.aliyuncs.com", "cn-hangzhou",
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", null,
                "FAKE-SIGN", "SMS_FAKE_TEMPLATE", "code", 2000, 2000);
    }

    private static SendSmsResponseBody body(String code, String message) {
        return new SendSmsResponseBody().setCode(code).setMessage(message)
                .setRequestId("req-fake").setBizId("biz-fake");
    }

    @Test
    @DisplayName("Code=OK 才受理成功（HTTP 概念不参与判定）")
    void okIsAccepted() {
        AliyunSmsSendGateway gateway = new AliyunSmsSendGateway(fakeProperties(),
                request -> body("OK", "OK"));
        SendResult result = gateway.send(FAKE_PHONE, FAKE_CODE);
        assertThat(result.accepted()).isTrue();
        assertThat(result.code()).isEqualTo("OK");
        assertThat(result.failureKind()).isNull();
        assertThat(result.requestId()).isEqualTo("req-fake");
        assertThat(result.bizId()).isEqualTo("biz-fake");
    }

    @Test
    @DisplayName("非 OK 业务码即使有 HTTP 200 式响应体也判失败并分类")
    void nonOkCodeIsRejected() {
        AliyunSmsSendGateway gateway = new AliyunSmsSendGateway(fakeProperties(),
                request -> body("isv.BUSINESS_LIMIT_CONTROL", "limit"));
        SendResult throttled = gateway.send(FAKE_PHONE, FAKE_CODE);
        assertThat(throttled.accepted()).isFalse();
        assertThat(throttled.failureKind()).isEqualTo(FailureKind.THROTTLED);

        AliyunSmsSendGateway configGateway = new AliyunSmsSendGateway(fakeProperties(),
                request -> body("isv.SMS_TEMPLATE_ILLEGAL", "template"));
        SendResult config = configGateway.send(FAKE_PHONE, FAKE_CODE);
        assertThat(config.accepted()).isFalse();
        assertThat(config.failureKind()).isEqualTo(FailureKind.CONFIGURATION);

        AliyunSmsSendGateway dependencyGateway = new AliyunSmsSendGateway(fakeProperties(),
                request -> body("isv.OUT_OF_SERVICE", "down"));
        assertThat(dependencyGateway.send(FAKE_PHONE, FAKE_CODE).failureKind())
                .isEqualTo(FailureKind.DEPENDENCY);
    }

    @Test
    @DisplayName("响应缺 Code 字段 ⇒ 失败（不得视为成功）")
    void missingCodeIsFailure() {
        AliyunSmsSendGateway gateway = new AliyunSmsSendGateway(fakeProperties(),
                request -> new SendSmsResponseBody().setMessage("no code"));
        SendResult result = gateway.send(FAKE_PHONE, FAKE_CODE);
        assertThat(result.accepted()).isFalse();
        assertThat(result.failureKind()).isEqualTo(FailureKind.DEPENDENCY);
        assertThat(result.message()).contains("missing Code");
    }

    @Test
    @DisplayName("TeaException 按 code 分类（凭据/签名类 → 配置类）")
    void teaExceptionClassified() {
        AliyunSmsSendGateway gateway = new AliyunSmsSendGateway(fakeProperties(), request -> {
            throw new TeaException(Map.of("code", "isv.SMS_SIGNATURE_ILLEGAL",
                    "message", "signature illegal",
                    "data", Map.of("RequestId", "req-tea")));
        });
        SendResult result = gateway.send(FAKE_PHONE, FAKE_CODE);
        assertThat(result.accepted()).isFalse();
        assertThat(result.failureKind()).isEqualTo(FailureKind.CONFIGURATION);
        assertThat(result.code()).isEqualTo("isv.SMS_SIGNATURE_ILLEGAL");
        assertThat(result.requestId()).isEqualTo("req-tea");
    }

    @Test
    @DisplayName("超时/IO 异常 → 依赖类（可退避重试，但短信非幂等）")
    void transportExceptionIsDependency() {
        AliyunSmsSendGateway gateway = new AliyunSmsSendGateway(fakeProperties(), request -> {
            throw new SocketTimeoutException("read timed out");
        });
        SendResult result = gateway.send(FAKE_PHONE, FAKE_CODE);
        assertThat(result.accepted()).isFalse();
        assertThat(result.failureKind()).isEqualTo(FailureKind.DEPENDENCY);
    }

    @Test
    @DisplayName("templateParam 为正确 JSON 且支持自定义键名与转义")
    void templateParamJsonEscaped() {
        assertThat(AliyunSmsSendGateway.templateParam("code", "123456"))
                .isEqualTo("{\"code\":\"123456\"}");
        assertThat(AliyunSmsSendGateway.templateParam("verifyCode", "a\"b\\c"))
                .isEqualTo("{\"verifyCode\":\"a\\\"b\\\\c\"}");
    }

    @Test
    @DisplayName("发送请求携带 phone/sign/template/templateParam（假 caller 记录）")
    void requestCarriesConfiguredFields() {
        List<SendSmsRequest> captured = new ArrayList<>();
        AliyunSmsSendGateway gateway = new AliyunSmsSendGateway(fakeProperties(), request -> {
            captured.add(request);
            return body("OK", "OK");
        });
        gateway.send(FAKE_PHONE, FAKE_CODE);
        assertThat(captured).hasSize(1);
        SendSmsRequest request = captured.get(0);
        assertThat(request.getPhoneNumbers()).isEqualTo(FAKE_PHONE);
        assertThat(request.getSignName()).isEqualTo("FAKE-SIGN");
        assertThat(request.getTemplateCode()).isEqualTo("SMS_FAKE_TEMPLATE");
        assertThat(request.getTemplateParam()).isEqualTo("{\"code\":\"" + FAKE_CODE + "\"}");
    }
}

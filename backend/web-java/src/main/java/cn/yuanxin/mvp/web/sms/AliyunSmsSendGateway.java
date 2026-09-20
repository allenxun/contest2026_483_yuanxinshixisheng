package cn.yuanxin.mvp.web.sms;

import com.aliyun.dysmsapi20170525.Client;
import com.aliyun.dysmsapi20170525.models.SendSmsRequest;
import com.aliyun.dysmsapi20170525.models.SendSmsResponseBody;
import com.aliyun.tea.TeaException;
import com.aliyun.teaopenapi.models.Config;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * 阿里云短信 V2.0 适配器——<b>全应用唯一</b>接触 {@code com.aliyun.*} SDK 的类。
 *
 * <p><b>成功判定：仅当响应体业务 {@code Code} 严格等于 {@code "OK"}</b>；HTTP 状态、
 * 响应非空、BizId 存在等都不代表成功。任何其它 {@code Code}、缺失 {@code Code}、
 * {@link TeaException}、超时或其它异常一律视为失败，并按 {@link FailureKind} 分类。</p>
 *
 * <p><b>日志脱敏：</b>只记录业务 Code、RequestId、掩码手机号与异常类型名；绝不记录
 * 验证码、AccessKey/Secret/SecurityToken、完整手机号或异常全文。</p>
 *
 * <p>模板参数 {@code TemplateParam} 为 JSON 字符串，键名取
 * {@code app.sms.aliyun.template-param-name}（默认 {@code code}），值经 JSON 转义。</p>
 */
public class AliyunSmsSendGateway implements SmsSendGateway {

    private static final Logger log = LoggerFactory.getLogger(AliyunSmsSendGateway.class);

    /** SDK 调用的最小接缝（仅测试替换；生产走 {@link #defaultCaller}）。 */
    interface SmsCaller {
        SendSmsResponseBody call(SendSmsRequest request) throws Exception;
    }

    private final AliyunSmsProperties properties;
    private final SmsCaller caller;

    public AliyunSmsSendGateway(AliyunSmsProperties properties) {
        this(properties, defaultCaller(properties));
    }

    AliyunSmsSendGateway(AliyunSmsProperties properties, SmsCaller caller) {
        this.properties = Objects.requireNonNull(properties, "properties");
        this.caller = Objects.requireNonNull(caller, "caller");
    }

    private static SmsCaller defaultCaller(AliyunSmsProperties properties) {
        Config config = new Config()
                .setAccessKeyId(properties.accessKeyId())
                .setAccessKeySecret(properties.accessKeySecret())
                .setRegionId(properties.regionId())
                .setEndpoint(properties.endpoint())
                .setConnectTimeout(properties.connectTimeoutMillis())
                .setReadTimeout(properties.readTimeoutMillis());
        if (properties.securityToken() != null) {
            config.setSecurityToken(properties.securityToken());
        }
        try {
            Client client = new Client(config);
            return request -> client.sendSms(request).getBody();
        } catch (Exception initFailure) {
            // 仅记录异常类型，不回显凭据/配置值。
            throw new IllegalStateException("aliyun sms client init failed: "
                    + initFailure.getClass().getSimpleName());
        }
    }

    @Override
    public SendResult send(String phone, String code) {
        SendSmsRequest request = new SendSmsRequest()
                .setPhoneNumbers(phone)
                .setSignName(properties.signName())
                .setTemplateCode(properties.templateCode())
                .setTemplateParam(templateParam(properties.templateParamName(), code));
        try {
            return mapBody(caller.call(request), phone);
        } catch (TeaException platformFailure) {
            FailureKind kind = FailureKind.classify(platformFailure.getCode());
            String requestId = requestIdOf(platformFailure);
            log.warn("aliyun sms rejected kind={} code={} requestId={} phone={}",
                    kind, safe(platformFailure.getCode()), safe(requestId), SmsMasking.maskPhone(phone));
            return SendResult.failed(kind, platformFailure.getCode(),
                    platformFailure.getMessage(), requestId, null);
        } catch (Exception transportFailure) {
            log.warn("aliyun sms transport error kind=DEPENDENCY exception={} phone={}",
                    transportFailure.getClass().getSimpleName(), SmsMasking.maskPhone(phone));
            return SendResult.failed(FailureKind.DEPENDENCY, null,
                    transportFailure.getClass().getSimpleName(), null, null);
        }
    }

    private SendResult mapBody(SendSmsResponseBody body, String phone) {
        String code = body == null ? null : body.getCode();
        if (code == null || code.isBlank()) {
            log.warn("aliyun sms response missing Code kind=DEPENDENCY phone={}",
                    SmsMasking.maskPhone(phone));
            return SendResult.failed(FailureKind.DEPENDENCY, code,
                    "response missing Code",
                    body == null ? null : body.getRequestId(),
                    body == null ? null : body.getBizId());
        }
        if ("OK".equals(code)) {
            log.info("aliyun sms accepted code=OK requestId={} bizId={} phone={}",
                    safe(body.getRequestId()), safe(body.getBizId()), SmsMasking.maskPhone(phone));
            return SendResult.accepted(code, body.getMessage(), body.getRequestId(), body.getBizId());
        }
        FailureKind kind = FailureKind.classify(code);
        log.warn("aliyun sms rejected kind={} code={} requestId={} phone={}",
                kind, safe(code), safe(body.getRequestId()), SmsMasking.maskPhone(phone));
        return SendResult.failed(kind, code, body.getMessage(), body.getRequestId(), body.getBizId());
    }

    /** {@code {"<name>":"<value>"}}，键名与值均做 JSON 转义。 */
    static String templateParam(String name, String value) {
        return "{\"" + escapeJson(name) + "\":\"" + escapeJson(value) + "\"}";
    }

    private static String escapeJson(String raw) {
        if (raw == null) {
            return "";
        }
        StringBuilder out = new StringBuilder(raw.length() + 8);
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.toString();
    }

    private static String requestIdOf(TeaException failure) {
        Object data = failure.getData() == null ? null : failure.getData().get("RequestId");
        return data == null ? null : String.valueOf(data);
    }

    private static String safe(String value) {
        return value == null ? "<none>" : value;
    }
}

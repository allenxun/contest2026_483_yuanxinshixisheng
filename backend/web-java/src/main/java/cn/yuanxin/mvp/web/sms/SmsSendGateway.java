package cn.yuanxin.mvp.web.sms;

/**
 * 短信发送缝：{@link AliyunSmsCodeProvider} 只依赖本接口；真实 SDK 触点全部收敛在
 * {@link AliyunSmsSendGateway}。测试用假实现即可，不发真实短信。
 */
public interface SmsSendGateway {

    /**
     * 发送验证码短信。
     *
     * @param phone E.164 手机号（调用方保证格式；实现须掩码记录）
     * @param code  待发送的验证码（实现不得记录该值）
     * @return 受理结果；仅 {@link SendResult#accepted()} 为 true 表示平台受理
     */
    SendResult send(String phone, String code);
}

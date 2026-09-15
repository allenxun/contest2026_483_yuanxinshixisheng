package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;
import java.util.List;

/**
 * 真实阿里云短信装配（B 自有）：仅当 {@code app.sms.provider=aliyun} <b>且</b>
 * {@code app.providers.mode != disabled}（{@link SmsProviderEnabledCondition}）时装配
 * {@link AliyunSmsSendGateway} 与 {@link AliyunSmsCodeProvider}。
 *
 * <p><b>优先级</b>：{@code app.providers.mode=disabled} 高于 {@code app.sms.provider}
 * ——能力显式关闭时短信走 A 的 disabled 占位（503），真实适配器不装配。</p>
 *
 * <p><b>启动期校验</b>：{@code provider=aliyun} 时若 access-key-id / access-key-secret /
 * sign-name / template-code 任一缺失，则在创建网关 bean 时抛 {@link IllegalStateException}
 * 拒绝启动；消息只列缺失<b>键名</b>，绝不含任何值。**不通过试发短信校验**（计费接口）。</p>
 *
 * <p>新类位于 {@code cn.yuanxin.mvp.web.sms} 包且类名不以 {@code Disabled} 开头 ⇒
 * {@code ProductionFailClosedValidator.isDouble()} 不会把 {@link AliyunSmsCodeProvider}
 * 误判为替身，生产 {@code app.env=production} 下可作为真实的 SmsCodeProvider 通过校验。</p>
 */
@Configuration
@ConditionalOnProperty(name = "app.sms.provider", havingValue = "aliyun")
@Conditional(SmsProviderEnabledCondition.class)
@EnableConfigurationProperties({AliyunSmsProperties.class, SmsRiskProperties.class})
public class SmsProvidersConfig {

    @Bean
    public SmsSendGateway smsSendGateway(AliyunSmsProperties properties) {
        List<String> missing = properties.missingRequiredKeys();
        if (!missing.isEmpty()) {
            // 只输出键名，绝不回显任何配置值。
            throw new IllegalStateException("app.sms.provider=aliyun missing required config keys: "
                    + missing + " (values are never logged)");
        }
        return new AliyunSmsSendGateway(properties);
    }

    @Bean
    public SmsCodeProvider aliyunSmsCodeProvider(SmsSendGateway smsSendGateway,
                                                 SmsRiskProperties riskProperties,
                                                 SmsStateStore smsStateStore) {
        // 状态后端由 app.state.provider 决定（SmsStateStoreConfig）：memory=进程内，redis=跨实例一致。
        return new AliyunSmsCodeProvider(smsSendGateway, riskProperties, Clock.systemUTC(),
                smsStateStore);
    }
}

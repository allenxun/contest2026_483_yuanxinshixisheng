package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.config.AppProperties;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

/**
 * 真实短信装配条件：{@code app.providers.mode != disabled}。
 *
 * <p>配合 {@code @ConditionalOnProperty(app.sms.provider=aliyun)} 使用，表达优先级：</p>
 * <pre>app.providers.mode=disabled （能力显式关闭） &gt; app.sms.provider=aliyun</pre>
 *
 * <p>即：只要 {@code mode=disabled}，短信一律由 A 的 {@code DisabledProvidersConfig}
 * 占位（运行时 503），真实适配器不装配。mode 归一（null/blank→doubles）复用 A 的
 * {@link AppProperties.Providers#mode()}，不重复实现。</p>
 */
public class SmsProviderEnabledCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        String mode = new AppProperties.Providers(
                context.getEnvironment().getProperty("app.providers.mode")).mode();
        return !"disabled".equals(mode);
    }
}

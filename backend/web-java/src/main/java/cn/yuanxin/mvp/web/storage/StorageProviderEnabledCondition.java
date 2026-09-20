package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.config.AppProperties;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

/**
 * 真实 OSS 装配条件：{@code app.providers.mode != disabled}。配合
 * {@code @ConditionalOnProperty(app.storage.provider=aliyun)}，表达优先级：
 * <pre>app.providers.mode=disabled （能力显式关闭） &gt; app.storage.provider=aliyun</pre>
 * 即 {@code mode=disabled} 时存储走 A 的 disabled 占位（运行时 503），真实适配器不装配。
 * mode 归一再利用 A 的 {@link AppProperties.Providers#mode()}。
 */
public class StorageProviderEnabledCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        String mode = new AppProperties.Providers(
                context.getEnvironment().getProperty("app.providers.mode")).mode();
        return !"disabled".equals(mode);
    }
}

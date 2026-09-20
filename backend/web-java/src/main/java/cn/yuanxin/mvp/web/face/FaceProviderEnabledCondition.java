package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.config.AppProperties;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

/**
 * 真实人脸装配条件：{@code app.providers.mode != disabled}。配合
 * {@code app.face.provider=insightface|aliyun} 表达优先级：
 * <pre>app.providers.mode=disabled （能力显式关闭） &gt; app.face.provider</pre>
 * mode 归一再利用 A 的 {@link AppProperties.Providers#mode()}。
 */
public class FaceProviderEnabledCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        String mode = new AppProperties.Providers(
                context.getEnvironment().getProperty("app.providers.mode")).mode();
        return !"disabled".equals(mode);
    }
}

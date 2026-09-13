package cn.yuanxin.mvp.web.face;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

/**
 * {@code app.face.provider=aliyun} 的<b>早期启动期拒绝</b>（红线 3）。
 *
 * <p>阿里云人脸 provider 目前<b>只有配置边界</b>（{@link AliyunFaceProperties}），<b>没有实现</b>。
 * 选择它必须拒绝启动并给出明确诊断，<b>绝不</b>静默回退 doubles、<b>绝不</b>提供假实现；
 * 也<b>不臆造</b>任何阿里云人脸 API 调用。</p>
 *
 * <p>守卫实现为 {@link BeanFactoryPostProcessor}（static {@code @Bean} 声明，避免早实例化告警），
 * 在 {@code refresh()} 的 {@code invokeBeanFactoryPostProcessors} 阶段执行，<b>早于</b>常规单例
 * 实例化与构造注入——否则会先报"缺 {@code FaceProvider}"而掩盖真实原因。</p>
 *
 * <p>{@code mode=disabled} 时本配置不激活（{@link FaceProviderEnabledCondition}）——能力显式
 * 关闭优先，走 A 的 disabled 占位。</p>
 */
@Configuration
@ConditionalOnProperty(name = "app.face.provider", havingValue = "aliyun")
@Conditional(FaceProviderEnabledCondition.class)
public class AliyunFaceBoundaryConfig {

    @Bean
    static AliyunFaceBoundaryGuard aliyunFaceBoundaryGuard() {
        return new AliyunFaceBoundaryGuard();
    }

    /** 早期拒绝：只说明事实与可选项，不回显任何配置值。 */
    static final class AliyunFaceBoundaryGuard implements BeanFactoryPostProcessor {

        @Override
        public void postProcessBeanFactory(ConfigurableListableBeanFactory beanFactory) {
            throw new IllegalStateException("app.face.provider=aliyun is not implemented: only a"
                    + " configuration boundary (app.face.aliyun.*) exists; use app.face.provider=doubles"
                    + " or insightface");
        }
    }
}

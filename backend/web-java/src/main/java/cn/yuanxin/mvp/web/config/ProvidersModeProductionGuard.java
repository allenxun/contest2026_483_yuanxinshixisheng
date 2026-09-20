package cn.yuanxin.mvp.web.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.util.Set;

/**
 * 生产信号 + {@code app.providers.mode=doubles} 的<b>早期明确拒绝</b>（B 自有，配置选择与诊断）。
 *
 * <p><b>为什么需要它：</b>{@link ProductionFailClosedValidator} 只在
 * {@code app.env=production} 时激活，覆盖不到 {@code prod}/{@code production}
 * profile 但 {@code app.env≠production} 的<b>矛盾组合</b>；此时上一轮的
 * {@link NonProductionCondition} 只是让替身配置不装配，最终报出的是
 * {@code NoSuchBeanDefinitionException}（例如“缺 SessionProvider”），把真正原因
 * “生产信号下不允许 doubles”掩盖掉。本守卫补上这一诊断。</p>
 *
 * <p><b>判据：</b>出现任一生产信号（生效 profiles 含 {@code prod}/{@code production}，
 * 或 {@code app.env} {@code trim()} 后忽略大小写等于 {@code production}）<b>且</b>
 * {@code app.providers.mode} 归一后为 {@code doubles} ⇒ 抛
 * {@link IllegalStateException} 使启动 fail-fast。判据与
 * {@link NonProductionCondition} 完全一致（复用其 {@code effectiveProfiles}/
 * {@code isNonProduction} 语义），mode 归一再利用 {@link AppProperties.Providers#mode()}。</p>
 *
 * <p><b>早于常规单例实例化：</b>本类实现 {@link BeanFactoryPostProcessor}，
 * 其 {@link #postProcessBeanFactory} 在 {@code AbstractApplicationContext.refresh()}
 * 的 {@code invokeBeanFactoryPostProcessors} 阶段执行，<b>先于</b>
 * {@code finishBeanFactoryInitialization} 对常规单例的实例化与构造注入。因此它
 * 一定抢在“缺 {@code SessionProvider}”等注入失败之前抛出诊断异常（对比
 * {@code DocsProductionGuard} 用 {@code SmartInitializingSingleton}，晚于注入失败）。</p>
 *
 * <p><b>三者分工：</b>本守卫 = 早期配置诊断（生产信号 + doubles 明确不允许）；
 * {@link ProductionFailClosedValidator} = {@code app.env=production} 下的实现完备性
 * 校验（端口是否为真实实现）；{@link NonProductionCondition} = 装配门（决定替身
 * 配置是否激活）。</p>
 *
 * <p>异常消息只输出生产信号取值（生效 profiles、{@code app.env}）与 mode，不含数据源
 * URL/用户名/口令/对象存储凭据等敏感内容。</p>
 */
@Component
public class ProvidersModeProductionGuard implements BeanFactoryPostProcessor, EnvironmentAware {

    private static final Logger log = LoggerFactory.getLogger(ProvidersModeProductionGuard.class);

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void postProcessBeanFactory(ConfigurableListableBeanFactory beanFactory) throws BeansException {
        if (NonProductionCondition.isNonProduction(environment)) {
            return;
        }
        String mode = new AppProperties.Providers(environment.getProperty("app.providers.mode")).mode();
        if (!"doubles".equals(mode)) {
            return;
        }
        Set<String> profiles = NonProductionCondition.effectiveProfiles(environment);
        String appEnv = environment.getProperty("app.env", "dev");
        String message = "production fail-closed: app.providers.mode=doubles is not allowed"
                + " under production signals (effective-profiles=" + profiles
                + ", app.env=" + appEnv
                + "); configure app.providers.mode=real with production implementations,"
                + " or app.providers.mode=disabled to explicitly disable capabilities";
        log.error(message);
        throw new IllegalStateException(message);
    }
}

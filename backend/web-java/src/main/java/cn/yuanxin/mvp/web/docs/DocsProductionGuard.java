package cn.yuanxin.mvp.web.docs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * API 文档的生产 fail-closed 护栏（B 自有，独立于 A 的
 * {@code ProductionFailClosedValidator}）。
 *
 * <p>与项目既有 fail-closed 教义一致：{@code app.env=production} 时若
 * springdoc 的 api-docs 或 swagger-ui 任一被启用，直接拒绝启动——生产绝不
 * 暴露可交互的 API 文档/调试面。生产 profile 中 application.yml 已显式
 * {@code enabled: false}；本类兜底“被命令行/环境变量强行打开”的情况。</p>
 *
 * <p>只在 {@code app.env=production} 时注册（{@link ConditionalOnProperty}），
 * dev/test 完全不参与。</p>
 */
@Component
@ConditionalOnProperty(name = "app.env", havingValue = "production")
public class DocsProductionGuard implements SmartInitializingSingleton {

    private static final Logger log = LoggerFactory.getLogger(DocsProductionGuard.class);

    private final Environment environment;

    public DocsProductionGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void afterSingletonsInstantiated() {
        boolean apiDocs = environment.getProperty("springdoc.api-docs.enabled", Boolean.class, false);
        boolean swaggerUi = environment.getProperty("springdoc.swagger-ui.enabled", Boolean.class, false);
        if (apiDocs || swaggerUi) {
            String msg = "production fail-closed: springdoc API docs must be disabled in production"
                    + " (springdoc.api-docs.enabled=" + apiDocs
                    + ", springdoc.swagger-ui.enabled=" + swaggerUi
                    + "); refusing to start with an exposed API documentation surface";
            log.error(msg);
            throw new IllegalStateException(msg);
        }
    }
}

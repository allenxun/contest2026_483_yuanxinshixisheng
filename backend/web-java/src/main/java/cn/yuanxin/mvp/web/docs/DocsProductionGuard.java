package cn.yuanxin.mvp.web.docs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * API 文档的生产 fail-closed 护栏（B 自有，独立于 A 的
 * {@code ProductionFailClosedValidator}）。
 *
 * <p><b>始终注册</b>（无条件 {@link ConditionalOnProperty}，见 fixed BLOCKER）：
 * 不能只按 {@code app.env=production} 判定——否则 {@code prod} profile 被
 * {@code app.env=dev} 覆盖时护栏不注册，而 springdoc starter 自身自动配置
 * （{@code springdoc.api-docs.enabled} 缺省视为开启）仍会暴露
 * {@code /v3/api-docs} 与 {@code /swagger-ui/**}。</p>
 *
 * <p>运行时生产信号（任一成立即视为生产）：active profile 含 {@code prod}，
 * 或 {@code app.env=production}（忽略大小写）。文档开启判定与 springdoc 缺省
 * 语义一致：{@code springdoc.api-docs.enabled} / {@code springdoc.swagger-ui.enabled}
 * 未显式设为 {@code false} 即按“可能开启”保守处理。</p>
 *
 * <p>生效时机：{@link SmartInitializingSingleton#afterSingletonsInstantiated()}
 * 在 bean 工厂预实例化结束时调用，早于 {@code finishRefresh()} 启动嵌入式 Web
 * 服务器——因此抛异常时端口尚未监听、springdoc 端点从未对外暴露（是“启动失败”
 * 而非“先起后关”）；与 A 的 {@code ProductionFailClosedValidator} 同一时机。</p>
 */
@Component
public class DocsProductionGuard implements SmartInitializingSingleton {

    private static final Logger log = LoggerFactory.getLogger(DocsProductionGuard.class);

    private static final String API_DOCS_KEY = "springdoc.api-docs.enabled";
    private static final String SWAGGER_UI_KEY = "springdoc.swagger-ui.enabled";

    private final Environment environment;

    public DocsProductionGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void afterSingletonsInstantiated() {
        boolean prodProfile = environment.acceptsProfiles(Profiles.of("prod"));
        String appEnv = environment.getProperty("app.env");
        boolean prodEnv = appEnv != null && "production".equalsIgnoreCase(appEnv.trim());
        if (!prodProfile && !prodEnv) {
            return;
        }
        // 与 springdoc 缺省一致：未显式 false 即视为可能开启（保守口径）。
        boolean apiDocs = effectivelyEnabled(API_DOCS_KEY);
        boolean swaggerUi = effectivelyEnabled(SWAGGER_UI_KEY);
        if (!apiDocs && !swaggerUi) {
            return;
        }
        List<String> enabled = new ArrayList<>();
        if (apiDocs) {
            enabled.add(API_DOCS_KEY);
        }
        if (swaggerUi) {
            enabled.add(SWAGGER_UI_KEY);
        }
        String msg = "production fail-closed: refusing to start with springdoc API docs enabled in a"
                + " production context (production signals: active-profile-prod=" + prodProfile
                + ", app.env=" + appEnv + "; enabled switches: " + enabled
                + "); set both " + API_DOCS_KEY + "=false and " + SWAGGER_UI_KEY + "=false";
        log.error(msg);
        throw new IllegalStateException(msg);
    }

    /** 缺省（未配置）视为开启，只有显式 false 才算关闭——对齐 springdoc matchIfMissing=true。 */
    private boolean effectivelyEnabled(String key) {
        return Boolean.TRUE.equals(environment.getProperty(key, Boolean.class, Boolean.TRUE));
    }
}

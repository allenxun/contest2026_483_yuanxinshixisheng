package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.auth.DeviceCredentialProvider;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.media.StoragePort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 生产 fail closed 启动校验（app.env=production 时激活；prod profile 经
 * application.yml 设置该属性）：任一认证/媒体端口若无真实实现
 * （没有 bean、只有 *.testdouble.* 替身、或 Disabled* 占位），启动失败，
 * 服务绝不带着可绕过的认证/存储能力上线（digest §6；A/decisions #7）。
 *
 * <p>这是"生产配置缺能力→fail closed"的机器执行点；README 同步说明。</p>
 */
@Component
@ConditionalOnProperty(name = "app.env", havingValue = "production")
public class ProductionFailClosedValidator implements SmartInitializingSingleton {

    private static final Logger log = LoggerFactory.getLogger(ProductionFailClosedValidator.class);

    private final ApplicationContext context;
    private final AppProperties props;

    public ProductionFailClosedValidator(ApplicationContext context, AppProperties props) {
        this.context = context;
        this.props = props;
    }

    @Override
    public void afterSingletonsInstantiated() {
        List<String> problems = new ArrayList<>();
        requireReal(problems, "SessionProvider", SessionProvider.class);
        requireReal(problems, "SmsCodeProvider", SmsCodeProvider.class);
        requireReal(problems, "DeviceCredentialProvider", DeviceCredentialProvider.class);
        requireReal(problems, "FaceProvider", FaceProvider.class);
        requireReal(problems, "StoragePort", StoragePort.class);
        // 媒体授权 fail closed（oracle round-2 R2-1/R2-6）：无条件执行，独立于
        // MediaAccessPolicy bean 装配（@ConditionalOnMissingBean 可能被覆盖跳过）。
        if (props.media().allowAnyAuthenticated()) {
            problems.add("app.media.allow-any-authenticated=true (open media read is refused in production)");
        }
        if (!props.media().defaultMode()) {
            problems.add("app.media.access-mode=" + props.media().accessModeOrDefault()
                    + " (production requires deny-all until a business @Primary MediaAccessPolicy is installed)");
        }
        if (!problems.isEmpty()) {
            String msg = "production fail-closed: unsafe production configuration -> " + problems
                    + " (configure app.providers.mode=real with production implementations and"
                    + " app.media.access-mode=deny-all; test doubles may never serve production,"
                    + " and open/owner media reads need a business @Primary MediaAccessPolicy)";
            log.error(msg);
            throw new IllegalStateException(msg);
        }
    }

    private void requireReal(List<String> problems, String label, Class<?> port) {
        Map<String, ?> beans = context.getBeansOfType(port);
        boolean real = beans.values().stream().anyMatch(b -> !isDouble(b.getClass()));
        if (!real) {
            problems.add(label + (beans.isEmpty() ? "=absent" : "=doubles/disabled only"));
        }
    }

    static boolean isDouble(Class<?> clazz) {
        String pkg = clazz.getPackage() == null ? "" : clazz.getPackage().getName();
        return pkg.contains(".testdouble") || clazz.getSimpleName().startsWith("Disabled")
                || (clazz.isAnonymousClass() && clazz.getEnclosingClass() != null
                        && "DisabledProvidersConfig".equals(clazz.getEnclosingClass().getSimpleName()));
    }
}

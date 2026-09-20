package cn.yuanxin.mvp.web.care;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.util.Set;

/**
 * C 域生产用人脸核验防线（防线二）：即便 dev/test 条件被绕过（例如混合 profile
 * 或未来配置变更），生产上下文也绝不允许选中非 fail-closed 的
 * {@link CareFaceVerifier}。
 *
 * <p>{@code afterPropertiesSet}：当 {@code app.env=production} 或生效 profiles 含
 * {@code prod}/{@code production}，而实际选中的实现不是
 * {@link FailClosedCareFaceVerifier}（例如 {@link MemberBindingFaceDouble}）时，
 * 抛出 {@link IllegalStateException} 使启动 fail-fast（消息不含任何配置值/凭据）。
 * dev/test 上下文 no-op。</p>
 */
@Component
public class CareFaceVerifierProductionGuard implements InitializingBean {

    private static final Logger log = LoggerFactory.getLogger(CareFaceVerifierProductionGuard.class);

    private final Environment environment;
    private final CareFaceVerifier selectedFaceVerifier;

    public CareFaceVerifierProductionGuard(Environment environment,
                                           CareFaceVerifier selectedFaceVerifier) {
        this.environment = environment;
        this.selectedFaceVerifier = selectedFaceVerifier;
    }

    @Override
    public void afterPropertiesSet() {
        if (isProductionContext()
                && !(selectedFaceVerifier instanceof FailClosedCareFaceVerifier)) {
            String message = "production fail-closed: a non-fail-closed CareFaceVerifier was"
                    + " selected in a production context; only FailClosedCareFaceVerifier is allowed";
            log.error(message);
            throw new IllegalStateException(message);
        }
    }

    private boolean isProductionContext() {
        if ("production".equalsIgnoreCase(environment.getProperty("app.env", "dev"))) {
            return true;
        }
        Set<String> profiles = CareDevTestCondition.effectiveProfiles(environment);
        return profiles.contains("prod") || profiles.contains("production");
    }
}

package cn.yuanxin.mvp.web.devices.proof;

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
 * B 自有证明端口生产 fail-closed 校验（{@code app.env=production} 时激活）。
 *
 * <p>凡 {@link PairingProofVerifier}/{@link ConnectionProofVerifier} 只有
 * dev/test 替身（{@code DevTestDouble*}）或缺失，启动失败——绝不带着未验证的
 * 客户端自填字段能力上线。本类<b>不修改</b> A 的
 * {@code ProductionFailClosedValidator}，只在自己的包内守自己的端口。</p>
 */
@Component
@ConditionalOnProperty(name = "app.env", havingValue = "production")
public class DeviceProofFailClosedValidator implements SmartInitializingSingleton {

    private static final Logger log = LoggerFactory.getLogger(DeviceProofFailClosedValidator.class);

    private final ApplicationContext context;

    public DeviceProofFailClosedValidator(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void afterSingletonsInstantiated() {
        List<String> problems = new ArrayList<>();
        requireReal(problems, "PairingProofVerifier", PairingProofVerifier.class);
        requireReal(problems, "ConnectionProofVerifier", ConnectionProofVerifier.class);
        if (!problems.isEmpty()) {
            String msg = "device proof fail-closed: production requires real device proof"
                    + " implementations -> " + problems;
            log.error(msg);
            throw new IllegalStateException(msg);
        }
    }

    private void requireReal(List<String> problems, String label, Class<?> port) {
        Map<String, ?> beans = context.getBeansOfType(port);
        boolean real = beans.values().stream().anyMatch(b -> !isDouble(b.getClass()));
        if (!real) {
            problems.add(label + (beans.isEmpty() ? "=absent" : "=test-double only"));
        }
    }

    static boolean isDouble(Class<?> clazz) {
        return clazz.getSimpleName().startsWith("DevTestDouble");
    }
}

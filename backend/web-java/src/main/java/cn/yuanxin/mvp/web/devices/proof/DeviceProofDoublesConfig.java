package cn.yuanxin.mvp.web.devices.proof;

import cn.yuanxin.mvp.web.config.NonProductionCondition;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

/**
 * 证明端口测试替身接线（仅<b>非生产环境</b>：{@link NonProductionCondition}，
 * 即 {@code app.env != production} 且生效 profiles 不含 prod/production；且
 * {@code app.providers.mode=doubles}，默认开启）。环境与实现选择解耦后
 * {@code local} 等自定义环境名同样装配；生产信号下本配置不激活，缺真实实现即被
 * B 自有 fail-closed 校验拒绝。
 */
@Configuration
@Conditional(NonProductionCondition.class)
@ConditionalOnProperty(name = "app.providers.mode", havingValue = "doubles", matchIfMissing = true)
public class DeviceProofDoublesConfig {

    @Bean
    public PairingProofVerifier pairingProofVerifier() {
        return new DevTestDoublePairingProofVerifier();
    }

    @Bean
    public ConnectionProofVerifier connectionProofVerifier() {
        return new DevTestDoubleConnectionProofVerifier();
    }
}

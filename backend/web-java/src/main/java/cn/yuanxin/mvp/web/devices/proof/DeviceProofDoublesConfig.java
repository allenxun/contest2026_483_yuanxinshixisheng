package cn.yuanxin.mvp.web.devices.proof;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

/**
 * 证明端口 dev/test 替身接线（仅 {@code dev}/{@code test} profile 且
 * {@code app.providers.mode=doubles}，默认开启）。生产 profile 下本配置不激活，
 * 缺真实实现即被 B 自有 fail-closed 校验拒绝。
 */
@Configuration
@Profile({"dev", "test"})
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

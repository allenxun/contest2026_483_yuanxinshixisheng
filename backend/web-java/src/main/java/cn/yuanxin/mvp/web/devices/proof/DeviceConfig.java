package cn.yuanxin.mvp.web.devices.proof;

import cn.yuanxin.mvp.web.devices.DeviceProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

/**
 * 设备包配置入口（所有 profile 生效）：注册 {@link DeviceProperties}。
 *
 * <p>证明端口替身仅在 dev/test + providers.mode=doubles 下装配；生产必须由
 * 真实实现提供（否则 {@link DeviceProofFailClosedValidator} 拒绝启动）。
 * 本类与替身均位于 B 自有 devices 包，不修改 A 的
 * {@code ProductionFailClosedValidator}/testdouble。</p>
 */
@Configuration
@EnableConfigurationProperties(DeviceProperties.class)
public class DeviceConfig {
}

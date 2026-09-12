package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.auth.DeviceCredentialProvider;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.DeviceCredentialDouble;
import cn.yuanxin.mvp.web.testdouble.FaceProviderDouble;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import cn.yuanxin.mvp.web.testdouble.SmsCodeDouble;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.context.annotation.RequestScope;

import java.util.Arrays;

/**
 * 隔离测试替身接线：仅 dev/test profile 且 app.providers.mode=doubles
 * （默认）。生产 profile 下本配置不激活——缺真实提供方即启动失败
 * （fail closed，ProductionFailClosedValidator / 注入缺失）。
 */
@Configuration
@org.springframework.context.annotation.Profile({"dev", "test"})
@ConditionalOnProperty(name = "app.providers.mode", havingValue = "doubles", matchIfMissing = true)
public class TestDoubleProvidersConfig {

    @Bean
    public SessionProvider sessionProvider(JdbcTemplate jdbc) {
        return new InMemorySessionDouble(jdbc);
    }

    @Bean
    public SmsCodeProvider smsCodeProvider(
            @Value("${app.testdouble.sms.fixed-code:123456}") String fixedCode) {
        return new SmsCodeDouble(fixedCode);
    }

    @Bean
    public DeviceCredentialProvider deviceCredentialProvider(JdbcTemplate jdbc) {
        return new DeviceCredentialDouble(jdbc);
    }

    @Bean
    public FaceProvider faceProvider(
            @Value("${app.testdouble.face.classification:MATCHED}") String classification) {
        return new FaceProviderDouble(classification);
    }

    @Bean
    public StoragePort storagePort(AppProperties props, Environment environment,
            @Value("${APP_DOUBLE_STORAGE_FAIL_MODE:none}") String failMode) {
        requireNoProductionSignals(environment);
        // 受控失败注入仅在替身构造期读取；非法取值 → 装配期 fail fast。
        return new FileSystemStorageDouble(props.storage().devDir(), failMode);
    }

    /**
     * 双判据生产 fail-closed（对齐 DocsProductionGuard）：只要出现任一生产信号
     * ——激活 profile 含 {@code prod}，或 {@code app.env=production}——本测试替身
     * 配置就拒绝装配并 fail fast，使 {@code APP_DOUBLE_STORAGE_FAIL_MODE} 等注入
     * 在生产/混合 profile（prod,dev）与矛盾组合（prod profile + app.env=dev）下
     * 均不可达。生产刻意绕开本配置（{@code app.providers.mode=real}）时另有
     * ProductionFailClosedValidator 兜底。
     */
    private static void requireNoProductionSignals(Environment environment) {
        boolean prodProfile = environment.acceptsProfiles(Profiles.of("prod"));
        String appEnv = environment.getProperty("app.env");
        boolean prodEnv = appEnv != null && "production".equalsIgnoreCase(appEnv.trim());
        if (prodProfile || prodEnv) {
            throw new IllegalStateException("production fail-closed: test-double providers refused"
                    + " under production signals (active-profile-prod=" + prodProfile
                    + ", app.env=" + appEnv + ", activeProfiles="
                    + Arrays.toString(environment.getActiveProfiles())
                    + "); configure app.providers.mode=real with production implementations");
        }
    }
}

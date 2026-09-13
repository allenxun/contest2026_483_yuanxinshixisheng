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
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.context.annotation.RequestScope;

/**
 * 隔离测试替身接线：仅<b>非生产环境</b>（{@link NonProductionCondition}：
 * {@code app.env != production} 且生效 profiles 不含 prod/production）且
 * {@code app.providers.mode=doubles}（默认）时激活。环境（profile）与实现选择
 * （mode）已解耦：{@code local} 等自定义环境名同样装配替身；生产信号下本配置
 * 不激活——缺真实提供方即启动失败（fail closed，ProductionFailClosedValidator /
 * 注入缺失）。
 */
@Configuration
@Conditional(NonProductionCondition.class)
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
     * 双判据生产 fail-closed——<b>按设计不可达</b>，按授权保留既有防护。
     *
     * <p>本方法与 {@link NonProductionCondition} 复用<b>同一判据</b>
     * （{@code !NonProductionCondition.isNonProduction(environment)}），因此与装配条件层
     * <b>完全等价</b>，不再有强弱差异。拒装已提前到条件层与早期诊断守卫
     * {@link ProvidersModeProductionGuard}：出现任一生产信号（生效 profiles 含
     * {@code prod}/{@code production}，或 {@code app.env=production}）时，本配置根本
     * 不装配，{@code storagePort()} 从不被调用，故本方法在那些场景下不会被触发。</p>
     *
     * <p><b>定位说明（不得夸大）：</b>它只是与条件层判据一致的运行时复核，
     * <b>不</b>比条件层更强、<b>不</b>声称能覆盖条件层漏掉或写错的情形——若条件层门被
     * 移除/误写，本配置会随之一同装配或一同跳过（同一判据），本方法无法独立兜底。
     * 这里保留它仅因授权要求“保留相关防护”，并保留其异常消息的诊断价值（输出生产
     * 信号实际取值）。生产刻意绕开本配置（{@code app.providers.mode=real}）时另有
     * {@link ProductionFailClosedValidator} 做实现完备性校验。</p>
     */
    private static void requireNoProductionSignals(Environment environment) {
        if (NonProductionCondition.isNonProduction(environment)) {
            return;
        }
        String appEnv = environment.getProperty("app.env", "dev");
        throw new IllegalStateException("production fail-closed: test-double providers refused"
                + " under production signals (effective-profiles="
                + NonProductionCondition.effectiveProfiles(environment)
                + ", app.env=" + appEnv
                + "); configure app.providers.mode=real with production implementations");
    }
}

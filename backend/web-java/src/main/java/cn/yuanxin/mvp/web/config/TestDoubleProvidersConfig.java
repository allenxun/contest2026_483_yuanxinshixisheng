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
import org.springframework.core.env.Profiles;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.context.annotation.RequestScope;

import java.util.Arrays;

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
     * 双判据生产 fail-closed（对齐 DocsProductionGuard）——<b>现为纵深防御，按设计不可达</b>。
     *
     * <p>历史机制：本配置曾以 {@code @Profile({"dev","test"})} 为门，混合 profile
     * {@code prod,dev} 会因含 {@code dev} 而<b>照常装配</b>，故需要本方法在 {@code storagePort()}
     * 这个 {@code @Bean} 的装配期抛 {@link IllegalStateException} 拒装，使
     * {@code APP_DOUBLE_STORAGE_FAIL_MODE} 等注入在矛盾组合（prod profile + app.env=dev）下不可达。</p>
     *
     * <p>本轮环境/实现解耦后，本配置改由 {@link NonProductionCondition} 把关，<b>拒装提前到条件层</b>：
     * 出现任一生产信号（生效 profiles 含 {@code prod}/{@code production}，或 {@code app.env=production}）
     * 时整个配置根本不装配、替身从不被构造，故本方法在那些场景下<b>不会再被触发</b>（它与条件层用
     * 同样两条判据）。按授权“保留相关防护”刻意<b>不删除</b>，作为条件层被误改/被绕过时的兜底。</p>
     *
     * <p>两处判据的强弱差异（条件层更强，故兜底不会比条件层宽松）：本方法用
     * {@code acceptsProfiles(Profiles.of("prod"))}，对 profile 名<b>大小写敏感</b>且不回落
     * default profiles；{@link NonProductionCondition} 对 profile 名做小写归一并遵循
     * “active 优先、否则 default”的生效 profiles 语义。生产刻意绕开本配置
     * （{@code app.providers.mode=real}）时另有 ProductionFailClosedValidator 兜底。</p>
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

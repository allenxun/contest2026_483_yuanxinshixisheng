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
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.context.annotation.RequestScope;

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
    public StoragePort storagePort(AppProperties props) {
        return new FileSystemStorageDouble(props.storage().devDir());
    }
}

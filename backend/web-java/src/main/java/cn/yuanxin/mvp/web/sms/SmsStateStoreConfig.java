package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.state.AppStateProperties;
import cn.yuanxin.mvp.web.state.StateKeys;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

/**
 * 阿里云短信状态存储的装配（仅 {@code app.sms.provider=aliyun} 且
 * {@code app.providers.mode != disabled} 时激活，与 {@link SmsProvidersConfig} 同门）。
 *
 * <p><b>按 {@code app.state.provider} 选择实现</b>：</p>
 * <ul>
 *   <li>{@code memory}（默认，{@code matchIfMissing=true}）：{@link InMemorySmsStateStore}，
 *       逐字保留旧的内存语义（仅供隔离测试 / doubles）；</li>
 *   <li>{@code redis}：{@link RedisSmsStateStore}，注入 {@code StringRedisTemplate} 与
 *       {@link StateKeys}（后者由 {@code RedisStateConfig} 在 {@code app.state.provider=redis}
 *       下提供）。</li>
 * </ul>
 *
 * <p><b>优先级不变</b>：{@code app.providers.mode=disabled} 最高——本配置与
 * {@link SmsProvidersConfig} 一样使用 {@link SmsProviderEnabledCondition}，因此能力显式关闭时
 * 本 bean 不装配，短信仍走 disabled 占位。</p>
 *
 * <p><b>只用 {@code StringRedisTemplate}</b>：{@code RedisTemplate<Object,Object>} 默认 JDK
 * 序列化，会让 Lua 收到二进制 key。</p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "app.sms.provider", havingValue = "aliyun")
@Conditional(SmsProviderEnabledCondition.class)
@EnableConfigurationProperties(SmsRiskProperties.class)
public class SmsStateStoreConfig {

    /** 默认（未配置 {@code app.state.provider}）= 进程内实现，既有行为逐字不变。 */
    @Bean
    @ConditionalOnProperty(name = AppStateProperties.PROVIDER_KEY,
            havingValue = AppStateProperties.PROVIDER_MEMORY, matchIfMissing = true)
    public SmsStateStore inMemorySmsStateStore(SmsRiskProperties risk) {
        return new InMemorySmsStateStore(risk,
                InMemorySmsStateStore.DEFAULT_MAX_CHALLENGES,
                InMemorySmsStateStore.DEFAULT_MAX_TRACKED_PHONES);
    }

    /** {@code app.state.provider=redis}：跨实例一致的真实实现。 */
    @Bean
    @ConditionalOnProperty(name = AppStateProperties.PROVIDER_KEY,
            havingValue = AppStateProperties.PROVIDER_REDIS)
    public SmsStateStore redisSmsStateStore(StringRedisTemplate redis, StateKeys keys,
                                            SmsRiskProperties risk) {
        return new RedisSmsStateStore(redis, keys, risk);
    }
}

package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.SessionProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

import java.time.Clock;

/**
 * Redis 会话后端的装配入口（仅 {@code app.state.provider=redis} 时激活）。
 *
 * <p>与 {@code TestDoubleProvidersConfig.sessionProvider}（{@code app.state.provider=memory}）互斥，
 * 因此不会出现两个 {@link SessionProvider} 候选 bean。连接工厂与 {@code StringRedisTemplate}
 * 由 Boot 的 {@code RedisAutoConfiguration} 按标准 {@code spring.data.redis.*} 自动配置；
 * {@link StateKeys} 由 {@link RedisStateConfig} 提供。</p>
 *
 * <p>只注入 {@code StringRedisTemplate}（JDK 序列化的 {@code RedisTemplate<Object,Object>} 会让
 * Lua 收到二进制 key）。{@code proxyBeanMethods=false}：bean 方法之间不互相调用。</p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = AppStateProperties.PROVIDER_KEY,
        havingValue = AppStateProperties.PROVIDER_REDIS)
public class RedisSessionConfig {

    /**
     * {@link Clock} 用 {@code Clock.systemUTC()}（与既有装配一致；测试可直接构造
     * {@link RedisSessionProvider} 注入可控时钟）。
     */
    @Bean
    public SessionProvider redisSessionProvider(StringRedisTemplate stringRedisTemplate,
                                                StateKeys stateKeys, JdbcTemplate jdbc) {
        return new RedisSessionProvider(stringRedisTemplate, stateKeys, jdbc, Clock.systemUTC());
    }
}

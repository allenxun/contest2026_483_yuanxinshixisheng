package cn.yuanxin.mvp.web.state;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Redis 状态后端的装配入口（仅 {@code app.state.provider=redis} 时激活）。
 *
 * <p><b>刻意不自行创建 {@code LettuceConnectionFactory}</b>：连接工厂与
 * {@code StringRedisTemplate} 由 Spring Boot 的 {@code RedisAutoConfiguration} 按标准
 * {@code spring.data.redis.*} 属性自动配置，本项目不重复实现 host/port/password/database/
 * timeout/url/ssl/sentinel/cluster 的映射（重复实现只会漏掉边界情况）。本类只负责：</p>
 * <ol>
 *   <li>把 {@link AppStateProperties} 注册为 bean（供实现类读取键前缀）；</li>
 *   <li>暴露唯一的 {@link StateKeys} bean —— 所有键都必须经它构造。</li>
 * </ol>
 *
 * <p><b>只用 {@code StringRedisTemplate}</b>：自动配置的 {@code RedisTemplate<Object,Object>}
 * 默认使用 JDK 序列化，Lua 脚本里 {@code redis.call('GET', KEYS[1])} 收到的会是二进制而非字符串，
 * 表现为"键找不到"这类极难诊断的故障。实现类必须注入 {@code StringRedisTemplate}。</p>
 *
 * <p><b>启动期不主动连接 Redis</b>：Boot 的 {@code LettuceConnectionFactory} 默认
 * {@code eagerInitialization=false}，因此 Redis 不可达时上下文仍能启动、首个命令才失败 ⇒
 * 请求期 503 fail-closed（见 {@link RedisFailures}）。这是有意的：把"Redis 短暂不可用"
 * 放大成"整个应用起不来"更糟。<b>配置</b>错误则由 {@link StateStoreConfigGuard} 在启动早期
 * 明确拒绝。</p>
 *
 * <p>{@code proxyBeanMethods=false}：本类无需 CGLIB 增强（避免 @Configuration 代理带来的
 * 构造器可见性等历史坑），bean 方法之间不互相调用。</p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = AppStateProperties.PROVIDER_KEY,
        havingValue = AppStateProperties.PROVIDER_REDIS)
@EnableConfigurationProperties(AppStateProperties.class)
public class RedisStateConfig {

    /**
     * 键模型唯一入口。前缀来自 {@code app.state.redis.key-prefix}
     * （默认 {@link StateKeys#DEFAULT_PREFIX}）；测试应注入<b>独立随机前缀</b>以隔离，
     * 清理时只删自己的前缀。
     */
    @Bean
    public StateKeys stateKeys(AppStateProperties properties) {
        return new StateKeys(properties.redis().keyPrefix());
    }
}

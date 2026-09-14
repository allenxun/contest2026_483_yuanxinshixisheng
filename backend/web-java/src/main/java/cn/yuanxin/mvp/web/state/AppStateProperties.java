package cn.yuanxin.mvp.web.state;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.Locale;

/**
 * 会话与阿里云短信状态的存储后端配置（{@code app.state.*}）。
 *
 * <p><b>为什么只有一个开关</b>：会话（access/refresh）与短信状态（challenge、一次性核销、
 * 尝试计数、限流）都需要<b>跨实例一致</b>与<b>重启不丢</b>，不存在"只迁其中一个"的合理场景；
 * 两个开关只会制造半迁移的中间态（本项目已多次吃过"半成功危害"的亏）。</p>
 *
 * <p><b>取值</b>：</p>
 * <ul>
 *   <li>{@code memory}（默认）：现有进程内实现，<b>仅供隔离测试与 doubles</b>；
 *       应用重启即失效、多实例之间不共享；</li>
 *   <li>{@code redis}：跨实例一致的真实实现，联调与真实 provider 必须用它。</li>
 * </ul>
 *
 * <p><b>连接参数一律用 Spring Boot 标准 {@code spring.data.redis.*}</b>
 * （{@code host}/{@code port}/{@code password}/{@code database}/{@code timeout}/
 * {@code connect-timeout}/{@code url}），本类型<b>不</b>重复声明它们，也不做任何 fallback：
 * {@code spring.data.redis.url} 若设置会覆盖 host/port/username/password/database（Boot 语义）。</p>
 *
 * <p><b>fail fast</b>：非法 {@code provider} 取值在绑定期即抛
 * {@link IllegalArgumentException}（消息只含键名与被拒取值，不含任何凭据）；
 * {@link StateStoreConfigGuard} 另在启动早期做同样校验，避免非法值退化成
 * "两个 provider 都不装配 ⇒ 缺 bean"的难诊断错误。</p>
 *
 * <p><b>安全</b>：本类型不含任何凭据字段（Redis 口令由 Boot 的
 * {@code spring.data.redis.password} 承载，绝不在此重复声明），故无需脱敏 {@code toString()}；
 * {@code key-prefix} 是命名空间而非秘密。</p>
 */
@ConfigurationProperties(prefix = "app.state")
public record AppStateProperties(String provider, Redis redis) {

    /** 配置键名（用于装配条件与守卫消息，集中在此避免拼写漂移）。 */
    public static final String PROVIDER_KEY = "app.state.provider";
    public static final String KEY_PREFIX_KEY = "app.state.redis.key-prefix";

    public static final String PROVIDER_MEMORY = "memory";
    public static final String PROVIDER_REDIS = "redis";

    public AppStateProperties {
        provider = normalizeProvider(provider);
        redis = redis == null ? new Redis(null) : redis;
    }

    /**
     * 归一化 provider：null/空白 → {@link #PROVIDER_MEMORY}；否则 trim + 小写后必须是
     * {@code memory} 或 {@code redis}，<b>不接受任何其它值、不做猜测、不做 fallback</b>。
     */
    public static String normalizeProvider(String raw) {
        if (raw == null || raw.isBlank()) {
            return PROVIDER_MEMORY;
        }
        String value = raw.trim().toLowerCase(Locale.ROOT);
        if (!PROVIDER_MEMORY.equals(value) && !PROVIDER_REDIS.equals(value)) {
            throw new IllegalArgumentException("invalid " + PROVIDER_KEY + "=" + raw.trim()
                    + "; expected one of [" + PROVIDER_MEMORY + ", " + PROVIDER_REDIS + "]"
                    + " (no fallback: an unknown backend is never silently treated as memory)");
        }
        return value;
    }

    /** 是否使用 Redis 后端。 */
    public boolean redisEnabled() {
        return PROVIDER_REDIS.equals(provider);
    }

    /**
     * {@code app.state.redis.*}。
     *
     * @param keyPrefix 所有键的命名空间前缀；null/空白 → {@link StateKeys#DEFAULT_PREFIX}。
     *                  测试应使用<b>独立随机前缀</b>隔离，清理时只删自己的前缀（绝不 FLUSHDB）。
     */
    public record Redis(String keyPrefix) {
        public Redis {
            keyPrefix = StateKeys.normalizePrefix(keyPrefix);
        }
    }
}

package cn.yuanxin.mvp.web.state;

import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.net.URI;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

/**
 * opt-in 真实 Redis 测试的<b>共享</b>工具（orchestrator 所有；两条实施道只读使用，<b>不得修改</b>）。
 *
 * <p><b>为什么存在</b>：mock {@code StringRedisTemplate} 只能证明<b>调用序列</b>，无法证明
 * 并发核销只有一个赢家、Lua 是否真的在服务端执行、TTL 是否真的生效、序列化是否匹配、
 * 以及跨实例一致性——而这些正是本次迁移的核心风险。因此原子性/并发/TTL/跨实例/fail-closed
 * 这几类断言必须跑在<b>真实 Redis</b> 上。</p>
 *
 * <p><b>但它默认绝不运行</b>：只有显式提供 {@code -Dmvp.test.redis.url=redis://host:port/db}
 * （或环境变量 {@code MVP_TEST_REDIS_URL}）时才启用；否则 {@link #available()} 为 false，
 * 使用方必须以 {@code Assumptions.abort(...)} 让<b>整类跳过</b>。这样默认全量套件
 * <b>不需要任何 Redis</b>，不会给 CI 或其他包增加基础设施要求。</p>
 *
 * <p><b>隔离与清理纪律</b>：每次运行生成<b>独立随机键前缀</b>（{@link #randomPrefix(String)}），
 * 清理只 {@code SCAN} + {@code DEL} <b>自己前缀</b>的键（{@link #cleanup}）；
 * <b>绝不</b>使用 {@code FLUSHDB}/{@code FLUSHALL}（本地测试容器已把这两个命令与 {@code CONFIG}
 * 重命名禁用）。使用方必须把清理放进 {@code finally} 或 {@code @AfterEach}，
 * 使断言失败时也不残留键。</p>
 *
 * <p><b>输出纪律</b>：本类不打印任何 URL、口令、键、token、手机号或验证码；
 * {@link #describe()} 只返回"是否可用 + 数据库索引"这类非敏感摘要，供跳过/启用日志使用。</p>
 */
public final class RedisTestSupport {

    /** 系统属性名：opt-in 真实 Redis 的连接 URL（唯一开关）。 */
    public static final String URL_PROPERTY = "mvp.test.redis.url";
    /** 环境变量名：与 {@link #URL_PROPERTY} 等价，便于 shell 驱动。 */
    public static final String URL_ENV = "MVP_TEST_REDIS_URL";

    private static final SecureRandom RANDOM = new SecureRandom();

    private RedisTestSupport() {
    }

    /** 读取 opt-in 的连接 URL；未提供或空白 → empty（此时相关测试必须整类跳过）。 */
    public static Optional<String> redisUrl() {
        String fromProperty = System.getProperty(URL_PROPERTY);
        if (fromProperty != null && !fromProperty.isBlank()) {
            return Optional.of(fromProperty.trim());
        }
        String fromEnv = System.getenv(URL_ENV);
        if (fromEnv != null && !fromEnv.isBlank()) {
            return Optional.of(fromEnv.trim());
        }
        return Optional.empty();
    }

    /** 是否已 opt-in 真实 Redis。 */
    public static boolean available() {
        return redisUrl().isPresent();
    }

    /**
     * 非敏感摘要，仅用于跳过/启用日志：<b>不含</b>主机、端口、口令，只含数据库索引。
     * 例如 {@code enabled=true db=5} 或 {@code enabled=false}。
     */
    public static String describe() {
        Optional<String> url = redisUrl();
        if (url.isEmpty()) {
            return "enabled=false (set -D" + URL_PROPERTY + "=redis://host:port/db to enable)";
        }
        return "enabled=true db=" + databaseOf(url.get());
    }

    /**
     * 生成本次运行的独立随机键前缀，形如 {@code b-<lane>-<16 hex>-}。
     * 已通过 {@link StateKeys#normalizePrefix(String)} 的合法性校验（无空白、无 glob 元字符）。
     */
    public static String randomPrefix(String lane) {
        byte[] bytes = new byte[8];
        RANDOM.nextBytes(bytes);
        String safeLane = lane == null || lane.isBlank()
                ? "test"
                : lane.trim().toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]", "");
        return StateKeys.normalizePrefix("b-" + safeLane + "-" + HexFormat.of().formatHex(bytes));
    }

    /**
     * 建立一个独立的 {@link StringRedisTemplate}（Lettuce，standalone）。
     *
     * <p><b>只用 {@code StringRedisTemplate}</b>：{@code RedisTemplate<Object,Object>} 默认 JDK 序列化，
     * 会让 Lua 脚本收到二进制 key。调用方负责在使用后 {@link #close(RedisConnectionFactoryHolder)}
     * （或自行持有并关闭 {@link LettuceConnectionFactory}）。</p>
     *
     * @return 持有 template 与其连接工厂的句柄
     */
    public static RedisConnectionFactoryHolder connect() {
        String url = redisUrl().orElseThrow(() -> new IllegalStateException(
                "real-Redis tests require -D" + URL_PROPERTY + " (or " + URL_ENV + "); got none"));
        URI uri = URI.create(url);
        RedisStandaloneConfiguration configuration = new RedisStandaloneConfiguration();
        configuration.setHostName(uri.getHost() == null ? "127.0.0.1" : uri.getHost());
        configuration.setPort(uri.getPort() < 0 ? 6379 : uri.getPort());
        configuration.setDatabase(databaseOf(url));
        if (uri.getUserInfo() != null && !uriUserInfoBlank(uri.getUserInfo())) {
            String userInfo = uri.getUserInfo();
            int colon = userInfo.indexOf(':');
            if (colon > 0) {
                configuration.setUsername(userInfo.substring(0, colon));
                configuration.setPassword(userInfo.substring(colon + 1));
            } else {
                configuration.setPassword(userInfo);
            }
        }
        LettuceConnectionFactory factory = new LettuceConnectionFactory(configuration);
        factory.afterPropertiesSet();
        StringRedisTemplate template = new StringRedisTemplate(factory);
        template.afterPropertiesSet();
        return new RedisConnectionFactoryHolder(factory, template);
    }

    /**
     * 用 {@code SCAN} 列出<b>自己前缀</b>的键（分页、非阻塞）。
     *
     * <p><b>绝不用 {@code KEYS}</b>：{@code KEYS} 会遍历整个键空间并<b>阻塞 Redis 单线程</b>，
     * 在根的生产/共享实例上属真实运维风险。本方法用 {@code SCAN}（{@code COUNT} 提示 200）
     * 分页遍历，只匹配自己的前缀。</p>
     */
    public static List<String> scanKeys(StringRedisTemplate template, String prefix) {
        List<String> found = new ArrayList<>();
        try (Cursor<String> cursor = template.scan(
                ScanOptions.scanOptions().match(prefix + "*").count(200).build())) {
            while (cursor.hasNext()) {
                found.add(cursor.next());
            }
        }
        return found;
    }

    /**
     * 只删除<b>自己前缀</b>的键（{@code SCAN} + {@code DEL}），返回删除数量。
     * <b>绝不</b>调用 {@code FLUSHDB}/{@code FLUSHALL}，也<b>绝不</b>调用 {@code KEYS}
     * （见 {@link #scanKeys(StringRedisTemplate, String)}）。
     */
    public static long cleanup(StringRedisTemplate template, String prefix) {
        List<String> batch = scanKeys(template, prefix);
        if (batch.isEmpty()) {
            return 0L;
        }
        Long deleted = template.delete(batch);
        return deleted == null ? 0L : deleted;
    }

    /** 从 URL 解析数据库索引；缺省或非法 → 0（不抛错，避免测试基建本身成为失败源）。 */
    public static int databaseOf(String url) {
        try {
            URI uri = URI.create(url);
            String path = uri.getPath();
            if (path == null || path.length() < 2) {
                return 0;
            }
            return Integer.parseInt(path.substring(1));
        } catch (RuntimeException ex) {
            return 0;
        }
    }

    private static boolean uriUserInfoBlank(String userInfo) {
        return userInfo == null || userInfo.isBlank() || ":".equals(userInfo);
    }

    /** 关闭连接工厂（必须在测试结束时调用，避免泄漏连接与线程）。 */
    public static void close(RedisConnectionFactoryHolder holder) {
        if (holder != null) {
            holder.factory().destroy();
        }
    }

    /**
     * 连接句柄：{@code factory} 需由调用方在用毕后交给 {@link #close(RedisConnectionFactoryHolder)}。
     */
    public record RedisConnectionFactoryHolder(LettuceConnectionFactory factory,
                                               StringRedisTemplate template) {
    }
}

package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIf;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.time.Clock;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;

/**
 * opt-in 真实 Redis IT：证明 mock 无法证明的原子性/并发/TTL/跨实例/fail-closed。
 * 仅当提供 {@code -Dmvp.test.redis.url=redis://127.0.0.1:6399/5} 时运行，否则整类跳过。
 * 独立随机前缀隔离，每测后清理自己前缀的键（绝不 FLUSHDB）。
 */
@EnabledIf("redisOptedIn")
class RedisSessionConcurrencyIT {

    private static final UUID ACCOUNT = UUID.fromString("00000000-0000-4000-8000-0000000000cc");
    private static final int THREADS = 16;

    private static RedisTestSupport.RedisConnectionFactoryHolder redis;
    private String prefix;
    private JdbcTemplate jdbc;

    static boolean redisOptedIn() {
        return RedisTestSupport.available();
    }

    @BeforeAll
    static void connect() {
        assumeTrue(RedisTestSupport.available(),
                "set -Dmvp.test.redis.url=redis://host:port/db to run real-Redis tests");
        redis = RedisTestSupport.connect();
    }

    @AfterAll
    static void close() {
        RedisTestSupport.close(redis);
        redis = null;
    }

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        prefix = RedisTestSupport.randomPrefix("sess-conc");
        jdbc = mock(JdbcTemplate.class);
        lenient().when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(java.util.Collections.singletonList(new Object[]{"active", 5L}));
    }

    @AfterEach
    void tearDown() {
        if (redis != null && prefix != null) {
            RedisTestSupport.cleanup(redis.template(), prefix);
        }
    }

    @Test
    @DisplayName("并发 refresh（16 线程同一凭据）：恰好 1 个成功，其余 empty")
    void concurrentRefreshExactlyOneWinner() throws Exception {
        RedisSessionProvider provider = provider();
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-r", 5L);
        AtomicInteger success = new AtomicInteger();
        List<Throwable> unexpected = runConcurrently(THREADS, () -> {
            if (provider.refreshAppSession(s.refreshToken()).isPresent()) {
                success.incrementAndGet();
            }
        });
        assertThat(unexpected).as("竞争失败应是 empty 而非异常").isEmpty();
        assertThat(success.get()).as("refresh 一次性：并发下恰一个赢家").isEqualTo(1);
    }

    @Test
    @DisplayName("并发 revoke（16 线程同一 access）：恰好 1 个拿到 RevokedSession")
    void concurrentRevokeExactlyOneWinner() throws Exception {
        RedisSessionProvider provider = provider();
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-v", 5L);
        AtomicInteger success = new AtomicInteger();
        List<Throwable> unexpected = runConcurrently(THREADS, () -> {
            if (provider.revokeSession(s.accessToken()).isPresent()) {
                success.incrementAndGet();
            }
        });
        assertThat(unexpected).as("竞争失败应是 empty 而非异常").isEmpty();
        assertThat(success.get()).as("logout 恰好一次返回 RevokedSession").isEqualTo(1);
        assertThat(provider.authenticate(s.accessToken())).isEmpty();
    }

    @Test
    @DisplayName("跨实例一致：A 签发 → B 认证；A 撤销 → B 立即失效")
    void twoInstancesShareStateAcrossRestart() {
        RedisSessionProvider instanceA = provider();
        RedisSessionProvider instanceB = provider();
        SessionProvider.IssuedAppSession s = instanceA.createAppSession(ACCOUNT, "inst-x", 5L);
        assertThat(instanceB.authenticate(s.accessToken())).isPresent();

        assertThat(instanceA.revokeSession(s.accessToken())).isPresent();
        assertThat(instanceB.authenticate(s.accessToken())).isEmpty();
    }

    @Test
    @DisplayName("TTL 真实生效：会话键 TTL>0 且 ≤ 期望；不存在 TTL=-1 的会话键")
    void sessionKeysAlwaysCarryTtl() {
        RedisSessionProvider provider = provider();
        provider.createAppSession(ACCOUNT, "inst-ttl", 5L);
        provider.createGimbalSession(UUID.randomUUID(), 1L);

        Set<String> keys = redis.template().keys(prefix + "*");
        assertThat(keys).isNotEmpty();
        for (String key : keys) {
            Long ttl = redis.template().getExpire(key, TimeUnit.SECONDS);
            assertThat(ttl).as("every session key must have a TTL").isNotNull().isGreaterThan(0L);
            assertThat(ttl).as("no key may be left with TTL=-1").isNotEqualTo(-1L);
        }
    }

    @Test
    @DisplayName("清理契约：cleanup 后自己前缀键数为 0")
    void cleanupLeavesNoOwnKeys() {
        RedisSessionProvider provider = provider();
        provider.createAppSession(ACCOUNT, "inst-clean", 5L);
        assertThat(redis.template().keys(prefix + "*")).isNotEmpty();
        long deleted = RedisTestSupport.cleanup(redis.template(), prefix);
        assertThat(deleted).isPositive();
        assertThat(redis.template().keys(prefix + "*")).isEmpty();
    }

    @Test
    @DisplayName("fail-closed：不可达 Redis ⇒ 503 DEPENDENCY_UNAVAILABLE，绝不是 Optional.empty")
    void unreachableRedisFailsClosed() {
        RedisSessionProvider provider = unreachableProvider();
        assertThatThrownBy(() -> provider.authenticate("any-token"))
                .isInstanceOf(ApiException.class)
                .satisfies(t -> assertThat(((ApiException) t).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE)
                        .isNotNull());
        assertThatThrownBy(() -> provider.createAppSession(ACCOUNT, "inst", 1L))
                .isInstanceOf(ApiException.class)
                .satisfies(t -> assertThat(((ApiException) t).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
        assertThatThrownBy(() -> provider.refreshAppSession("some-refresh"))
                .isInstanceOf(ApiException.class)
                .satisfies(t -> assertThat(((ApiException) t).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
        assertThatThrownBy(() -> provider.revokeSession("some-access"))
                .isInstanceOf(ApiException.class)
                .satisfies(t -> assertThat(((ApiException) t).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    // ---------- helpers ----------

    private RedisSessionProvider provider() {
        return new RedisSessionProvider(redis.template(), new StateKeys(prefix), jdbc, Clock.systemUTC());
    }

    /** 指向不可达端口 1 的独立 provider（连接被拒 ⇒ 503）。 */
    private RedisSessionProvider unreachableProvider() {
        RedisStandaloneConfiguration configuration = new RedisStandaloneConfiguration();
        configuration.setHostName("127.0.0.1");
        configuration.setPort(1);
        configuration.setDatabase(0);
        LettuceConnectionFactory factory = new LettuceConnectionFactory(configuration);
        factory.afterPropertiesSet();
        StringRedisTemplate template = new StringRedisTemplate(factory);
        template.afterPropertiesSet();
        return new RedisSessionProvider(template, new StateKeys(prefix), jdbc, Clock.systemUTC());
    }

    private interface Action {
        void run() throws Exception;
    }

    private static List<Throwable> runConcurrently(int threads, Action action) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        List<Throwable> unexpected = java.util.Collections.synchronizedList(new java.util.ArrayList<>());
        try {
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    try {
                        start.await(30, TimeUnit.SECONDS);
                        action.run();
                    } catch (Throwable failure) {
                        // 竞争失败应是 empty（正常返回值），不是异常；异常一律记录供断言。
                        unexpected.add(failure);
                    } finally {
                        done.countDown();
                    }
                });
            }
            start.countDown();
            assertThat(done.await(30, TimeUnit.SECONDS)).isTrue();
            return List.copyOf(unexpected);
        } finally {
            pool.shutdownNow();
        }
    }
}

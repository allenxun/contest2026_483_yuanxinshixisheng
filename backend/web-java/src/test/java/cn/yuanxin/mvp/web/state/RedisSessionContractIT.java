package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.SessionProvider;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.condition.EnabledIf;
import org.springframework.jdbc.core.JdbcTemplate;

import java.time.Clock;

import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * 契约测试的 Redis 后端执行（<b>opt-in</b>）：仅当提供
 * {@code -Dmvp.test.redis.url=redis://127.0.0.1:6399/5}（或 {@code MVP_TEST_REDIS_URL}）时才运行，
 * 否则整类 abort（默认全量套件不需要 Redis）。用独立随机键前缀隔离并在每测后清理自己前缀。
 *
 * <p>与 {@code InMemorySessionContractTest} 共用同一组断言 ⇒ 防止两种后端实现漂移。</p>
 */
@EnabledIf("redisOptedIn")
class RedisSessionContractIT extends SessionProviderContractTest {

    private static RedisTestSupport.RedisConnectionFactoryHolder redis;
    private String prefix;

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

    @Override
    protected SessionProvider createProvider(JdbcTemplate jdbc) {
        prefix = RedisTestSupport.randomPrefix("sess-contract");
        return new RedisSessionProvider(redis.template(), new StateKeys(prefix), jdbc,
                Clock.systemUTC());
    }

    @Override
    protected void cleanup() {
        if (redis != null && prefix != null) {
            RedisTestSupport.cleanup(redis.template(), prefix);
        }
    }
}

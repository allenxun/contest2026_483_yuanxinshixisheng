package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.state.RedisTestSupport;
import cn.yuanxin.mvp.web.state.StateKeys;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * {@link RedisSmsStateStore} 的 L2 真实 Redis 集成测试（<b>默认整类跳过</b>）。
 *
 * <p>仅当显式提供 {@code -Dmvp.test.redis.url=redis://host:port/db}（或环境变量
 * {@code MVP_TEST_REDIS_URL}）时运行；否则 {@link BeforeAll} 以
 * {@link Assumptions#abort(String)} 让整类跳过。默认全量套件<b>不需要任何 Redis</b>。</p>
 *
 * <p><b>清理纪律</b>：每次测试用 {@link RedisTestSupport#randomPrefix(String)} 生成的独立前缀隔离，
 * {@link AfterEach} 只 {@code SCAN + DEL} 自己的前缀并断言剩余为 0；<b>绝不</b> FLUSHDB/FLUSHALL。</p>
 *
 * <p><b>输出纪律</b>：不打印 URL、口令、完整键、手机号或验证码。</p>
 */
class RedisSmsStateStoreIT {

    private static final String PHONE = "+8610000000000";
    private static final Instant FIXED_NOW = Instant.parse("2026-01-01T00:00:00Z"); // UTC+8 08:00:00

    private RedisTestSupport.RedisConnectionFactoryHolder holder;
    private StringRedisTemplate template;
    private StateKeys keys;
    private String prefix;

    @BeforeAll
    static void requireOptInRedis() {
        if (!RedisTestSupport.available()) {
            Assumptions.abort("real-Redis IT skipped: " + RedisTestSupport.describe());
        }
    }

    @BeforeEach
    void connect() {
        holder = RedisTestSupport.connect();
        template = holder.template();
        prefix = RedisTestSupport.randomPrefix("sms");
        keys = new StateKeys(prefix);
    }

    @AfterEach
    void tearDown() {
        try {
            if (template != null) {
                RedisTestSupport.cleanup(template, prefix);
                assertThat(template.keys(prefix + "*")).as("own keys fully cleaned").isEmpty();
            }
        } finally {
            RedisTestSupport.close(holder);
        }
    }

    private SmsRiskProperties defaults() {
        return new SmsRiskProperties(null, null, null, null, null, null);
    }

    private RedisSmsStateStore newStore() {
        return new RedisSmsStateStore(template, keys, defaults());
    }

    // ---------- 1) 并发一次性核销：恰好 1 个赢家 ----------

    @Test
    @DisplayName("32 线程同一 challengeId + 正确码：恰好 1 个拿到手机号，其余 empty，键已删除")
    void concurrentConsumeExactlyOneWinner() throws Exception {
        int threads = 32;
        RedisSmsStateStore store = newStore();
        String challengeId = "ch" + UUID.randomUUID().toString().replace("-", "");
        String code = "246810";
        store.createChallenge(challengeId, PHONE, code, FIXED_NOW, 300);
        String challengeKey = keys.smsChallenge(challengeId);

        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CyclicBarrier barrier = new CyclicBarrier(threads);
        AtomicInteger winners = new AtomicInteger();
        List<String> returned = Collections.synchronizedList(new ArrayList<>());
        List<Callable<Void>> tasks = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            tasks.add(() -> {
                barrier.await(30, TimeUnit.SECONDS);
                Optional<String> result = store.consumeChallenge(
                        challengeId, code, FIXED_NOW.plusSeconds(1), 5);
                if (result.isPresent()) {
                    winners.incrementAndGet();
                    returned.add(result.get());
                }
                return null;
            });
        }
        List<Future<Void>> futures = pool.invokeAll(tasks, 60, TimeUnit.SECONDS);
        pool.shutdownNow();
        for (Future<Void> future : futures) {
            future.get();
        }

        assertThat(winners.get()).as("跨实例/并发下只能有一个赢家").isEqualTo(1);
        assertThat(returned).containsExactly(PHONE);
        assertThat(template.hasKey(challengeKey)).as("成功核销后键必须删除").isFalse();
    }

    // ---------- 2) 尝试上限跨"实例"生效 ----------

    @Test
    @DisplayName("两个独立 store 共享同一 Redis：交替失败累计达上限后任何实例都不再成功")
    void attemptLimitSharedAcrossInstances() {
        SmsRiskProperties risk = new SmsRiskProperties(300, 3, 10, 10, 10, 60);
        RedisSmsStateStore instanceA = new RedisSmsStateStore(template, keys, risk);
        RedisSmsStateStore instanceB = new RedisSmsStateStore(template, keys, risk);
        String challengeId = "ch" + UUID.randomUUID().toString().replace("-", "");
        String code = "135790";
        instanceA.createChallenge(challengeId, PHONE, code, FIXED_NOW, 300);

        assertThat(instanceA.consumeChallenge(challengeId, "000000", FIXED_NOW, 3)).isEmpty();
        // 失败计数是 challenge 哈希的 att 字段，随键 TTL 一起过期 ⇒ 绝不出现 TTL=-1 的孤儿计数键。
        assertThat(template.getExpire(keys.smsChallenge(challengeId)))
                .as("失败尝试后计数键 TTL 必须 > 0").isGreaterThan(0L);
        assertThat(instanceB.consumeChallenge(challengeId, "000000", FIXED_NOW, 3)).isEmpty();
        assertThat(instanceA.consumeChallenge(challengeId, "000000", FIXED_NOW, 3)).isEmpty();

        // 达到上限后，正确码在任一实例都必须失败（且不返回手机号）。
        assertThat(instanceB.consumeChallenge(challengeId, code, FIXED_NOW, 3)).isEmpty();
        assertThat(instanceA.consumeChallenge(challengeId, code, FIXED_NOW, 3)).isEmpty();
        assertThat(template.hasKey(keys.smsChallenge(challengeId))).isFalse();
    }

    // ---------- 3) 无永不过期键（含负向对照） ----------

    @Test
    @DisplayName("负向对照：裸 INCR 留下 TTL=-1 的键（证明断言有判别力），随后删除")
    void bareIncrementLeavesNoTtlControlKey() {
        String controlKey = prefix + "probe:bare-incr";
        template.opsForValue().increment(controlKey);
        assertThat(template.getExpire(controlKey))
                .as("裸 INCR 必须留下永不过期键 TTL=-1（负向对照）").isEqualTo(-1L);
        template.delete(controlKey);
        assertThat(template.hasKey(controlKey)).isFalse();
    }

    @Test
    @DisplayName("三窗口计数键 TTL 均 > 0（INCR + EXPIRE 同脚本，绝无 TTL=-1）")
    void rateLimitKeysAlwaysExpire() {
        SmsThrottleWindows.Snapshot windows = SmsThrottleWindows.compute(FIXED_NOW);
        RedisSmsStateStore store = newStore();
        SmsStateStore.SendReservation reservation = store.reserveSend(PHONE, FIXED_NOW);
        assertThat(reservation.granted()).isTrue();

        for (String key : List.of(
                keys.smsRateLimit(PHONE, "m", windows.minuteBucket()),
                keys.smsRateLimit(PHONE, "h", windows.hourBucket()),
                keys.smsRateLimit(PHONE, "d", windows.dayBucket()))) {
            assertThat(template.hasKey(key)).as("窗口键存在").isTrue();
            assertThat(template.getExpire(key)).as("窗口键 TTL 必须 > 0").isGreaterThan(0L);
        }
    }

    // ---------- 4) 限流窗口（UTC+8 归一）----------

    @Test
    @DisplayName("同手机号分钟窗口超限 ⇒ store 层拒绝且 retry-after ∈ [1,60]，三键 TTL>0、桶名 UTC+8")
    void minuteWindowThrottleUsesUtcPlusEightBuckets() {
        SmsThrottleWindows.Snapshot windows = SmsThrottleWindows.compute(FIXED_NOW);
        // UTC+8 08:00:00 ⇒ 分钟桶 202601010800；这就是 UTC+8 自然窗口的归一证据。
        assertThat(windows.minuteBucket()).isEqualTo("202601010800");
        assertThat(windows.hourBucket()).isEqualTo("2026010108");
        assertThat(windows.dayBucket()).isEqualTo("20260101");

        RedisSmsStateStore store = newStore();
        assertThat(store.reserveSend(PHONE, FIXED_NOW).granted()).isTrue();
        SmsStateStore.SendReservation throttled = store.reserveSend(PHONE, FIXED_NOW);
        assertThat(throttled.granted()).isFalse();
        assertThat(throttled.retryAfterSeconds()).isBetween(1L, 60L);

        for (String key : List.of(
                keys.smsRateLimit(PHONE, "m", windows.minuteBucket()),
                keys.smsRateLimit(PHONE, "h", windows.hourBucket()),
                keys.smsRateLimit(PHONE, "d", windows.dayBucket()))) {
            assertThat(template.getExpire(key)).isGreaterThan(0L);
        }
    }

    // ---------- 5) 节流补偿 ----------

    @Test
    @DisplayName("远端未被受理 ⇒ 原子回退名额：二次预留后再补偿一次，计数回到 1")
    void releaseCompensatesReservedWindow() {
        SmsRiskProperties risk = new SmsRiskProperties(300, 5, 10, 10, 10, 60);
        RedisSmsStateStore store = new RedisSmsStateStore(template, keys, risk);
        SmsThrottleWindows.Snapshot windows = SmsThrottleWindows.compute(FIXED_NOW);
        String minuteKey = keys.smsRateLimit(PHONE, "m", windows.minuteBucket());

        SmsStateStore.SendReservation first = store.reserveSend(PHONE, FIXED_NOW);
        SmsStateStore.SendReservation second = store.reserveSend(PHONE, FIXED_NOW);
        assertThat(first.granted()).isTrue();
        assertThat(second.granted()).isTrue();
        assertThat(template.opsForValue().get(minuteKey)).isEqualTo("2");

        store.releaseSend(second, false); // 模拟远端发送未被受理
        assertThat(template.opsForValue().get(minuteKey))
                .as("补偿后计数与补偿前一致（2 - 1 = 1）").isEqualTo("1");

        store.releaseSend(first, false);
        assertThat(template.hasKey(minuteKey)).as("计数归零后键被删除，不留 TTL=-1 残留").isFalse();
    }

    // ---------- 6) fail-closed ----------

    @Test
    @DisplayName("不可达 Redis ⇒ 抛 ApiException 503 DEPENDENCY_UNAVAILABLE，绝不是 empty、绝不是 401")
    void unreachableRedisFailsClosed() {
        LettuceConnectionFactory factory = new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("127.0.0.1", 1));
        factory.afterPropertiesSet();
        try {
            RedisSmsStateStore store = new RedisSmsStateStore(
                    new StringRedisTemplate(factory), keys, defaults());

            ApiException reserveFailure = assertThrows(ApiException.class,
                    () -> store.reserveSend(PHONE, FIXED_NOW));
            assertThat(reserveFailure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
            assertThat(reserveFailure.getHttpStatus()).isEqualTo(503);

            String challengeId = "ch" + UUID.randomUUID().toString().replace("-", "");
            ApiException verifyFailure = assertThrows(ApiException.class,
                    () -> store.consumeChallenge(challengeId, "123456", FIXED_NOW, 5));
            assertThat(verifyFailure.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
            assertThat(verifyFailure.getHttpStatus()).isEqualTo(503);
        } finally {
            factory.destroy();
        }
    }

    // ---------- 7) 明文验证码不落 Redis ----------

    @Test
    @DisplayName("创建 challenge 后 Redis 值不含明文验证码，但含正确摘要；键不含手机号")
    void plaintextCodeNeverStoredInRedis() {
        RedisSmsStateStore store = newStore();
        String challengeId = "ch" + UUID.randomUUID().toString().replace("-", "");
        String code = "975310";
        store.createChallenge(challengeId, PHONE, code, FIXED_NOW, 300);

        String challengeKey = keys.smsChallenge(challengeId);
        assertThat(challengeKey).doesNotContain(PHONE);

        var entries = template.opsForHash().entries(challengeKey);
        String stored = entries.toString();
        assertThat(stored).as("明文验证码绝不落 Redis").doesNotContain(code);
        assertThat(stored).as("必须存以 challengeId 为盐的摘要")
                .contains(StateKeys.codeDigest(code, challengeId));
        assertThat(entries.get("ph")).isEqualTo(PHONE);
        assertThat(template.getExpire(challengeKey)).isGreaterThan(0L);
    }
}

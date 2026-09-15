package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIf;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.time.Clock;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * opt-in 真实 Redis IT：refresh 与 logout 交错的<b>不可复活</b>不变量（Oracle BLOCKER 1）。
 * 仅当提供 {@code -Dmvp.test.redis.url=redis://127.0.0.1:6399/5} 时运行，否则整类跳过。
 *
 * <p><b>为何只放在 Redis 侧</b>：{@code InMemorySessionDouble} 有同构竞态，但它是仅供隔离测试的
 * 替身、且是既有限制，本轮不修；共享契约测试不能包含本断言，否则内存后端会失败。</p>
 */
@EnabledIf("redisOptedIn")
class RedisSessionInterleaveIT {

    private static final UUID ACCOUNT = UUID.fromString("00000000-0000-4000-8000-0000000000dd");
    private static final int ROUNDS = 60;

    private static RedisTestSupport.RedisConnectionFactoryHolder redis;

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

    @Test
    @DisplayName("确定性交错：refresh 读完旧会话后 logout 抢先 → rotate 不得复活（返回 0/2，无新键）")
    void deterministicRefreshPausedThenLogoutCannotResurrect() throws Exception {
        String prefix = RedisTestSupport.randomPrefix("sess-il");
        try {
            // 用可阻塞的 JdbcTemplate 精确制造"refresh 已读旧会话、尚未 rotate"的窗口。
            CountDownLatch refreshAtDb = new CountDownLatch(1);
            CountDownLatch logoutDone = new CountDownLatch(1);
            JdbcTemplate blocking = mock(JdbcTemplate.class);
            when(blocking.query(anyString(), any(RowMapper.class), any())).thenAnswer(invocation -> {
                refreshAtDb.countDown();
                logoutDone.await(10, TimeUnit.SECONDS);
                return Collections.singletonList(new Object[]{"active", 5L});
            });

            RedisSessionProvider provider = new RedisSessionProvider(
                    redis.template(), new StateKeys(prefix), blocking, Clock.systemUTC());
            SessionProvider.IssuedAppSession session = provider.createAppSession(ACCOUNT, "inst-il", 5L);

            AtomicReference<Optional<SessionProvider.IssuedAppSession>> refreshed = new AtomicReference<>();
            AtomicReference<Throwable> refreshFailure = new AtomicReference<>();
            Thread refresh = new Thread(() -> {
                try {
                    refreshed.set(provider.refreshAppSession(session.refreshToken()));
                } catch (Throwable failure) {
                    refreshFailure.set(failure);
                }
            });
            refresh.start();

            assertThat(refreshAtDb.await(10, TimeUnit.SECONDS))
                    .as("refresh must reach the DB step before logout").isTrue();
            Optional<SessionProvider.RevokedSession> revoked = provider.revokeSession(session.accessToken());
            assertThat(revoked).as("logout must win at this point").isPresent();
            logoutDone.countDown();
            refresh.join(10_000);

            assertThat(refreshFailure.get()).isNull();
            assertThat(refreshed.get()).as("refresh must NOT resurrect the logged-out session").isEmpty();
            assertThat(RedisTestSupport.scanKeys(redis.template(), prefix))
                    .as("no session key may remain after logout wins").isEmpty();
        } finally {
            RedisTestSupport.cleanup(redis.template(), prefix);
        }
    }

    @Test
    @DisplayName("并发 refresh vs logout（60 轮）：恰一个成功；revoke 赢后无任何可认证会话")
    void concurrentRefreshAndLogoutExactlyOneWinnerAndNoResurrection() throws Exception {
        int bothSucceeded = 0;
        int bothEmpty = 0;
        int refreshWins = 0;
        int revokeWins = 0;
        for (int round = 0; round < ROUNDS; round++) {
            String prefix = RedisTestSupport.randomPrefix("sess-race");
            try {
                RedisSessionProvider provider = new RedisSessionProvider(
                        redis.template(), new StateKeys(prefix), activeJdbc(), Clock.systemUTC());
                SessionProvider.IssuedAppSession session =
                        provider.createAppSession(ACCOUNT, "inst-race", 5L);

                CyclicBarrier barrier = new CyclicBarrier(2);
                AtomicReference<Optional<SessionProvider.IssuedAppSession>> refresh =
                        new AtomicReference<>();
                AtomicReference<Optional<SessionProvider.RevokedSession>> revoke =
                        new AtomicReference<>();
                List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());
                Thread t1 = new Thread(() -> {
                    try {
                        barrier.await(10, TimeUnit.SECONDS);
                        refresh.set(provider.refreshAppSession(session.refreshToken()));
                    } catch (Throwable failure) {
                        errors.add(failure);
                    }
                });
                Thread t2 = new Thread(() -> {
                    try {
                        barrier.await(10, TimeUnit.SECONDS);
                        revoke.set(provider.revokeSession(session.accessToken()));
                    } catch (Throwable failure) {
                        errors.add(failure);
                    }
                });
                t1.start();
                t2.start();
                t1.join(10_000);
                t2.join(10_000);
                assertThat(errors).as("round %d: neither side may throw", round).isEmpty();

                boolean refreshed = refresh.get() != null && refresh.get().isPresent();
                boolean revoked = revoke.get() != null && revoke.get().isPresent();
                if (refreshed && revoked) {
                    bothSucceeded++;
                }
                if (!refreshed && !revoked) {
                    bothEmpty++;
                }
                if (refreshed) {
                    refreshWins++;
                    assertThat(provider.authenticate(session.accessToken()))
                            .as("round %d: refresh wins ⇒ old access must be invalid", round).isEmpty();
                }
                if (revoked) {
                    revokeWins++;
                    assertThat(provider.authenticate(session.accessToken()))
                            .as("round %d: revoke wins ⇒ old access invalid", round).isEmpty();
                    assertThat(RedisTestSupport.scanKeys(redis.template(), prefix))
                            .as("round %d: revoke wins ⇒ no resurrected session", round).isEmpty();
                }
            } finally {
                RedisTestSupport.cleanup(redis.template(), prefix);
            }
        }
        assertThat(bothSucceeded).as("不得出现 refresh 与 logout 都成功（复活）").isZero();
        assertThat(bothEmpty).as("恰好一个成功；不应两者都失败").isZero();
        assertThat(refreshWins + revokeWins).isEqualTo(ROUNDS);
    }

    private static JdbcTemplate activeJdbc() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        lenient().when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(Collections.singletonList(new Object[]{"active", 5L}));
        return jdbc;
    }
}

package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Answers;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.time.Clock;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * SUGGESTION 8：写脚本返回码校验测试。
 * <ul>
 *   <li>create/drop 返回非 1（或 null）⇒ 抛 {@link ApiException} 503 {@code DEPENDENCY_UNAVAILABLE}，
 *       绝不把未确认的 token 返回给调用方；</li>
 *   <li>rotate CAS 返回 0（refresh 已被消费）/2（会话已撤销）/null ⇒ {@code Optional.empty()}，
 *       绝不返回 {@code IssuedAppSession}；仅返回 1 才返回新 token。</li>
 * </ul>
 */
class RedisSessionProviderReturnCodeTest {

    private static final String PREFIX = "b-returncode:";
    private static final String SID = "11111111-2222-4333-8444-555555555555";
    private static final String AT_DIGEST = StateKeys.sha256Hex("access-token");
    private static final String RT_DIGEST = StateKeys.sha256Hex("refresh-token");
    private static final UUID ACCOUNT = UUID.fromString("00000000-0000-4000-8000-0000000000ff");

    private final AtomicReference<Long> nextExecuteCode = new AtomicReference<>(1L);
    private final List<List<String>> executedKeys = new java.util.ArrayList<>();
    private StateKeys keys;
    private StringRedisTemplate template;
    private HashOperations<String, String, String> hashes;
    private ValueOperations<String, String> values;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        keys = new StateKeys(PREFIX);
        values = mock(ValueOperations.class);
        hashes = mock(HashOperations.class);
        template = mock(StringRedisTemplate.class, invocation -> {
            switch (invocation.getMethod().getName()) {
                case "opsForValue":
                    return values;
                case "opsForHash":
                    return hashes;
                case "execute":
                    executedKeys.add((List<String>) invocation.getArgument(1));
                    return nextExecuteCode.get();
                default:
                    return Answers.RETURNS_DEFAULTS.answer(invocation);
            }
        });
    }

    @Test
    @DisplayName("createAppSession 返回码 0 ⇒ 503，绝不返回 token")
    void createAppNonOneAckThrows() {
        nextExecuteCode.set(0L);
        assertThatThrownBy(() -> provider(activeJdbc(5L)).createAppSession(ACCOUNT, "inst", 5L))
                .isInstanceOf(ApiException.class)
                .satisfies(t -> assertThat(((ApiException) t).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    @Test
    @DisplayName("createGimbalSession 返回码 null ⇒ 503，绝不返回 token")
    void createGimbalNullAckThrows() {
        nextExecuteCode.set(null);
        assertThatThrownBy(() -> provider(activeJdbc(5L)).createGimbalSession(UUID.randomUUID(), 1L))
                .isInstanceOf(ApiException.class)
                .satisfies(t -> assertThat(((ApiException) t).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    @Test
    @DisplayName("rotate 返回 1 ⇒ 返回新 token（正向）")
    void rotateCodeOneReturnsTokens() {
        nextExecuteCode.set(1L);
        stubReads(RT_DIGEST);
        assertThat(provider(activeJdbc(5L)).refreshAppSession("refresh-token")).isPresent();
    }

    @Test
    @DisplayName("rotate 返回 0（refresh 已被消费）⇒ empty，不返回 token")
    void rotateCodeZeroReturnsEmpty() {
        nextExecuteCode.set(0L);
        stubReads(RT_DIGEST);
        assertThat(provider(activeJdbc(5L)).refreshAppSession("refresh-token")).isEmpty();
    }

    @Test
    @DisplayName("rotate 返回 2（会话已撤销）⇒ empty，不返回 token")
    void rotateCodeTwoReturnsEmpty() {
        nextExecuteCode.set(2L);
        stubReads(RT_DIGEST);
        assertThat(provider(activeJdbc(5L)).refreshAppSession("refresh-token")).isEmpty();
    }

    @Test
    @DisplayName("rotate 返回 null ⇒ empty，不返回 token")
    void rotateNullReturnsEmpty() {
        nextExecuteCode.set(null);
        stubReads(RT_DIGEST);
        assertThat(provider(activeJdbc(5L)).refreshAppSession("refresh-token")).isEmpty();
    }

    @Test
    @DisplayName("drop 返回码 0 ⇒ 503（代次不符时的连带撤销未被确认）")
    void dropNonOneAckThrows() {
        nextExecuteCode.set(0L);
        stubReads(RT_DIGEST);
        assertThatThrownBy(() -> provider(activeJdbc(6L)).refreshAppSession("refresh-token"))
                .isInstanceOf(ApiException.class)
                .satisfies(t -> assertThat(((ApiException) t).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    // ---------- helpers ----------

    private RedisSessionProvider provider(JdbcTemplate jdbc) {
        return new RedisSessionProvider(template, keys, jdbc, Clock.systemUTC());
    }

    private void stubReads(String rtDigest) {
        when(values.get(anyString())).thenReturn(SID);
        Map<String, String> index = new HashMap<>();
        index.put("at", AT_DIGEST);
        index.put("rt", rtDigest);
        when(hashes.entries(keys.sessionById(SID))).thenReturn(index);
        Map<String, String> session = new HashMap<>();
        session.put("kind", "app");
        session.put("sid", SID);
        session.put("aid", ACCOUNT.toString());
        session.put("iid", "inst-returncode");
        session.put("rev", "5");
        when(hashes.entries(keys.sessionByAccessTokenDigest(AT_DIGEST))).thenReturn(session);
    }

    private static JdbcTemplate activeJdbc(long revision) {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        lenient().when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(java.util.Collections.singletonList(new Object[]{"active", revision}));
        return jdbc;
    }
}

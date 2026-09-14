package cn.yuanxin.mvp.web.state;

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
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * 判别力测试（不需 Redis）：证明 rotate/drop 传给 Lua 的 {@code KEYS[]} 是<b>完整具体键名</b>，
 * 而不是命名空间（{@code <prefix>sess:at:} 这类以 {@code :} 结尾的形式）。若实现退回"传命名空间 +
 * 脚本内拼接"，本测试的 {@code noneMatch(endsWith(":"))} 与逐键相等断言会失败。
 *
 * <p>用带默认 {@link Answers} 的 mock 记录 {@code execute(...)} 的第 2 个参数（KEYS 列表），
 * 避免 Mockito 的 varargs 匹配歧义。</p>
 */
class RedisSessionProviderKeyShapeTest {

    private static final String PREFIX = "b-keyshape:";
    private static final String SID = "11111111-2222-4333-8444-555555555555";
    private static final String AT_DIGEST = StateKeys.sha256Hex("access-token");
    private static final String RT_DIGEST = StateKeys.sha256Hex("refresh-token");
    private static final UUID ACCOUNT = UUID.fromString("00000000-0000-4000-8000-0000000000ee");

    private final List<List<String>> executedKeys = new ArrayList<>();
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
                    return 1L;
                default:
                    return Answers.RETURNS_DEFAULTS.answer(invocation);
            }
        });
    }

    @Test
    @DisplayName("rotate CAS：KEYS[] 全为完整具体键（旧 rt/旧 sid/旧 at/新 at/新 sid/新 rt），无命名空间")
    void rotatePassesConcreteKeys() {
        when(values.get(anyString())).thenReturn(SID);
        stubIndex(RT_DIGEST);
        stubSession();

        provider(activeJdbc(5L)).refreshAppSession("refresh-token");

        List<String> sentKeys = executedKeys.get(0);
        assertAllConcrete(sentKeys);
        assertThat(sentKeys).as("CAS KEYS: 旧 rt, 旧 sid, 旧 at, 新 at, 新 sid, 新 rt").hasSize(6);
        assertThat(sentKeys.get(0)).as("KEYS[1] 旧 rt").isEqualTo(keys.sessionByRefreshTokenDigest(RT_DIGEST));
        assertThat(sentKeys.get(1)).as("KEYS[2] 旧 sid").isEqualTo(keys.sessionById(SID));
        assertThat(sentKeys.get(2)).as("KEYS[3] 旧 access（由摘要具体构造）")
                .isEqualTo(keys.sessionByAccessTokenDigest(AT_DIGEST));
        assertThat(sentKeys.get(3)).startsWith(PREFIX + "sess:at:").doesNotEndWith(":");
        assertThat(sentKeys.get(4)).startsWith(PREFIX + "sess:sid:").doesNotEndWith(":");
        assertThat(sentKeys.get(5)).startsWith(PREFIX + "sess:rt:").doesNotEndWith(":");
        // 负向：命名空间形式绝不在 KEYS 里。
        assertThat(sentKeys).doesNotContain(keys.pattern("sess:at:"), keys.pattern("sess:rt:"));
    }

    @Test
    @DisplayName("drop（无 refresh）：KEYS[] 用 sidKey 作占位具体键，绝无命名空间/空串")
    void dropPassesConcreteKeysWithPlaceholderWhenNoRefresh() {
        when(values.get(anyString())).thenReturn(SID);
        stubIndex("");
        stubSession();

        provider(activeJdbc(6L)).refreshAppSession("refresh-token");

        List<String> sentKeys = executedKeys.get(0);
        assertAllConcrete(sentKeys);
        assertThat(sentKeys).hasSize(3);
        assertThat(sentKeys.get(0)).isEqualTo(keys.sessionById(SID));
        assertThat(sentKeys.get(1)).isEqualTo(keys.sessionByAccessTokenDigest(AT_DIGEST));
        assertThat(sentKeys.get(2)).as("无 refresh 时的占位必须是具体键").isEqualTo(keys.sessionById(SID));
        assertThat(sentKeys).doesNotContain(keys.pattern("sess:at:"), keys.pattern("sess:rt:"));
    }

    @Test
    @DisplayName("drop（有 refresh）：KEYS[] 含由摘要具体构造的 refresh 键")
    void dropPassesConcreteRefreshKeyWhenPresent() {
        when(values.get(anyString())).thenReturn(SID);
        stubIndex(RT_DIGEST);
        stubSession();

        provider(activeJdbc(6L)).refreshAppSession("refresh-token");

        List<String> sentKeys = executedKeys.get(0);
        assertAllConcrete(sentKeys);
        assertThat(sentKeys.get(2)).isEqualTo(keys.sessionByRefreshTokenDigest(RT_DIGEST));
        assertThat(sentKeys).doesNotContain(keys.pattern("sess:rt:"));
    }

    // ---------- helpers ----------

    private RedisSessionProvider provider(JdbcTemplate jdbc) {
        return new RedisSessionProvider(template, keys, jdbc, Clock.systemUTC());
    }

    private void stubIndex(String rtDigest) {
        Map<String, String> index = new HashMap<>();
        index.put("at", AT_DIGEST);
        index.put("rt", rtDigest);
        when(hashes.entries(keys.sessionById(SID))).thenReturn(index);
    }

    private void stubSession() {
        Map<String, String> session = new HashMap<>();
        session.put("kind", "app");
        session.put("sid", SID);
        session.put("aid", ACCOUNT.toString());
        session.put("iid", "inst-keyshape");
        session.put("rev", "5");
        when(hashes.entries(keys.sessionByAccessTokenDigest(AT_DIGEST))).thenReturn(session);
    }

    private static JdbcTemplate activeJdbc(long revision) {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        lenient().when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(java.util.Collections.singletonList(new Object[]{"active", revision}));
        return jdbc;
    }

    private static void assertAllConcrete(List<String> sentKeys) {
        assertThat(sentKeys).as("all KEYS must be concrete keys bounded by the prefix")
                .allSatisfy(key -> assertThat(key).startsWith(PREFIX));
        assertThat(sentKeys).as("no KEYS entry may be a namespace (namespaces end with ':')")
                .noneMatch(key -> key.endsWith(":"));
    }
}

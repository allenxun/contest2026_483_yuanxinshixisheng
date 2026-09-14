package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.jdbc.core.JdbcTemplate;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * Redis 后端的 {@link SessionProvider}（APP access/refresh + 云台会话）。仅
 * {@code app.state.provider=redis} 时装配；把会话状态从进程内存迁到 Redis，做到跨实例一致、
 * 重启不丢、原子轮换/撤销。
 *
 * <p><b>不变量（与 {@code InMemorySessionDouble} 逐条一致）</b></p>
 * <ul>
 *   <li>TTL：APP 会话 2 小时、云台会话 1 小时；refresh 凭据与其会话同 TTL（不新增旋钮）；</li>
 *   <li>token：32 字节 {@link SecureRandom} → URL-safe Base64（无填充），不透明；</li>
 *   <li>{@code sessionId} = {@code UUID.randomUUID()}，不摘要（T09/T13 需原值）；</li>
 *   <li>{@link #authenticate(String)} 只查 Redis 命中后返回<b>签发时快照</b>，<b>不</b>重读 DB；
 *       每请求 DB 复核仍由 {@code PrincipalRevalidator} 负责；</li>
 *   <li>refresh：先原子领取 refresh 凭据（{@code GETDEL}），再查 DB 与会话<b>签发时的
 *       auth_revision 快照</b>比对；不一致/账号非 active ⇒ 连带撤销该会话并返回 empty，
 *       <b>绝不</b>重新捕获当前 revision 复活旧代次；成功则沿用同一 revision 快照并令旧 access
 *       立即失效（Lua 原子轮换）；</li>
 *   <li>{@code revokeSession} 恰好一次（Lua {@code HGETALL}+{@code DEL}），并发登出只有一个赢家。</li>
 * </ul>
 *
 * <p><b>fail-closed</b>：所有 Redis 访问一律经 {@link RedisFailures#call(String, java.util.function.Supplier)}
 * 包装 ⇒ 连接失败/命令超时/服务端错误统一 503 {@code DEPENDENCY_UNAVAILABLE}；<b>绝不</b>把后端故障
 * 降级成 {@code Optional.empty()}（那会伪装成 401），也<b>绝不</b>回退内存实现。业务判定（会话不存在、
 * refresh 已用完、revision 不符）用正常返回值表达。</p>
 *
 * <p><b>键模型</b>：全部经 {@link StateKeys} 构造。轮换（rotate）与连带撤销（drop）把调用方
 * <b>已知的具体键名</b>（经 {@link StateKeys#sessionByAccessTokenDigest(String)} /
 * {@link StateKeys#sessionByRefreshTokenDigest(String)} 由摘要构造）经 {@code KEYS[]} 传入，
 * 脚本内<b>无</b>命名空间拼接，满足 Redis 官方"所有被访问键显式声明于 KEYS[]"。</p>
 *
 * <p><b>唯一保留的拼接（结构性不可避免，如实披露）</b>：logout 撤销脚本
 * （{@code session-revoke.lua}）需要删除的 {@code sess:sid:*} / {@code sess:rt:*} 键名依赖脚本内
 * {@code HGETALL} 读到的 {@code sid}/{@code rt} 摘要，调用方在脚本执行前无法知道；而"读取 + 删除"必须
 * 原子才能保证并发登出<b>恰好一个赢家</b>。因此该脚本以命名空间（{@code <prefix>sess:sid:} /
 * {@code <prefix>sess:rt:}）传入 {@code KEYS[]} 并由脚本拼接运行期摘要。</p>
 * <ul>
 *   <li><b>standalone：正确</b>（本地与根当前部署即此形态）。</li>
 *   <li><b>cluster：不成立</b>——官方要求脚本访问的所有键必须显式声明于 {@code KEYS[]} 且同 hash slot。</li>
 * </ul>
 * <p><b>cluster 迁移路径（本轮不实现）</b>：① {@code sess:at:<digest>} 只存 sessionId；
 * ② 会话数据集中到带 hash tag 的单键 {@code sess:{<sessionId>}}；③ 撤销改为两步——先
 * {@code GETDEL sess:at:<digest>} → sid 保证恰好一次，再以完整 {@code KEYS[]}（全部带同一 hash tag）
 * 执行第二个脚本删除。详见 {@code session-revoke.lua} 头部注释。</p>
 *
 * <p><b>脱敏</b>：不打印 token / sessionId / accountId / installationId / 键 / Redis 主机。</p>
 */
public class RedisSessionProvider implements SessionProvider {

    static final Duration APP_SESSION_TTL = Duration.ofHours(2);
    static final Duration GIMBAL_SESSION_TTL = Duration.ofHours(1);

    private static final String KIND_APP = "app";
    private static final String KIND_GIMBAL = "gimbal";

    private static final DefaultRedisScript<Long> CREATE_SCRIPT =
            script("redis/session-create.lua", Long.class);
    private static final DefaultRedisScript<Long> ROTATE_SCRIPT =
            script("redis/session-rotate.lua", Long.class);
    private static final DefaultRedisScript<Long> DROP_SCRIPT =
            script("redis/session-drop.lua", Long.class);
    @SuppressWarnings("rawtypes")
    private static final DefaultRedisScript<List> REVOKE_SCRIPT =
            script("redis/session-revoke.lua", List.class);

    private final StringRedisTemplate template;
    private final StateKeys keys;
    /** 可为 null（仅纯装配/跨实例一致性测试用）；refresh 的 revision 复核在 null 时跳过。 */
    private final JdbcTemplate jdbc;
    private final Clock clock;
    private final SecureRandom random = new SecureRandom();

    public RedisSessionProvider(StringRedisTemplate template, StateKeys keys, JdbcTemplate jdbc,
                                Clock clock) {
        this.template = template;
        this.keys = keys;
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Override
    public Optional<AuthenticatedPrincipal> authenticate(String accessToken) {
        if (accessToken == null || accessToken.isBlank()) {
            return Optional.empty();
        }
        String accessKey = keys.sessionByAccessToken(accessToken);
        Map<String, String> fields = RedisFailures.call("authenticate",
                () -> template.<String, String>opsForHash().entries(accessKey));
        if (fields.isEmpty() || fields.get("sid") == null) {
            return Optional.empty();
        }
        long expiry = parseLong(fields.get("exp"), Long.MAX_VALUE);
        if (expiry <= clock.instant().toEpochMilli()) {
            // 逻辑 TTL 由 Redis 保证；此处为防御性判定（不依赖物理删除时刻）。
            return Optional.empty();
        }
        PrincipalType type = KIND_GIMBAL.equals(fields.get("kind"))
                ? PrincipalType.GIMBAL : PrincipalType.APP;
        String sessionId = fields.get("sid");
        long rev = parseLong(fields.get("rev"), 0L);
        if (type == PrincipalType.GIMBAL) {
            return Optional.of(AuthenticatedPrincipal.gimbal(
                    UUID.fromString(fields.get("aid")), rev, sessionId));
        }
        return Optional.of(AuthenticatedPrincipal.app(
                UUID.fromString(fields.get("aid")), emptyToNull(fields.get("iid")), sessionId, rev));
    }

    @Override
    public IssuedAppSession createAppSession(UUID accountId, String installationId, long authRevision) {
        Instant now = clock.instant();
        Instant expiresAt = now.plus(APP_SESSION_TTL);
        String access = randomToken();
        String refresh = randomToken();
        String sessionId = UUID.randomUUID().toString();
        String accessKey = keys.sessionByAccessToken(access);
        String refreshKey = keys.sessionByRefreshToken(refresh);
        String sidKey = keys.sessionById(sessionId);
        RedisFailures.call("create-app-session", () -> template.execute(CREATE_SCRIPT,
                List.of(accessKey, sidKey, refreshKey),
                Long.toString(APP_SESSION_TTL.getSeconds()), KIND_APP, sessionId,
                accountId.toString(), nullToEmpty(installationId), Long.toString(authRevision),
                Long.toString(now.toEpochMilli()), Long.toString(expiresAt.toEpochMilli()),
                StateKeys.sha256Hex(access), StateKeys.sha256Hex(refresh), "1"));
        return new IssuedAppSession(access, refresh, accountId, installationId, expiresAt);
    }

    @Override
    public Optional<IssuedAppSession> refreshAppSession(String refreshCredential) {
        if (refreshCredential == null || refreshCredential.isBlank()) {
            return Optional.empty();
        }
        String refreshKey = keys.sessionByRefreshToken(refreshCredential);
        // ① 原子领取：GETDEL 只有一个赢家；领取失败是业务判定（refresh 已用过）⇒ empty。
        String sessionId = RedisFailures.call("claim-refresh",
                () -> template.opsForValue().getAndDelete(refreshKey));
        if (sessionId == null || sessionId.isBlank()) {
            return Optional.empty();
        }
        String sidKey = keys.sessionById(sessionId);
        Map<String, String> index = RedisFailures.call("read-session-index",
                () -> template.<String, String>opsForHash().entries(sidKey));
        String atDigest = index.get("at");
        if (atDigest == null || atDigest.isBlank()) {
            return Optional.empty();
        }
        String rtDigest = nullToEmpty(index.get("rt"));
        String atKey = keys.sessionByAccessTokenDigest(atDigest);
        Map<String, String> session = RedisFailures.call("read-session",
                () -> template.<String, String>opsForHash().entries(atKey));
        if (session.isEmpty() || session.get("aid") == null) {
            return Optional.empty();
        }
        UUID accountId = UUID.fromString(session.get("aid"));
        String installationId = emptyToNull(session.get("iid"));
        long snapshotRevision = parseLong(session.get("rev"), Long.MIN_VALUE);

        // 具体键名（无命名空间拼接）：drop/rotate 的所有被访问键都显式声明于 KEYS[]。
        String oldAccessKey = keys.sessionByAccessTokenDigest(atDigest);
        boolean hasRefresh = !rtDigest.isEmpty();
        // refresh 摘要为空时用 sidKey 作占位具体键 + hasRefresh=0，脚本跳过删除（绝不传命名空间/空串）。
        String oldRefreshKey = hasRefresh ? keys.sessionByRefreshTokenDigest(rtDigest) : sidKey;

        if (!stillSameGeneration(accountId, snapshotRevision)) {
            // 账号 disabled 或代次已变：连带撤销本会话，绝不复活旧代次。
            RedisFailures.call("drop-invalid-session", () -> template.execute(DROP_SCRIPT,
                    List.of(sidKey, oldAccessKey, oldRefreshKey), hasRefresh ? "1" : "0"));
            return Optional.empty();
        }

        Instant now = clock.instant();
        Instant expiresAt = now.plus(APP_SESSION_TTL);
        String newAccess = randomToken();
        String newRefresh = randomToken();
        String newSessionId = UUID.randomUUID().toString();
        RedisFailures.call("rotate-refresh", () -> template.execute(ROTATE_SCRIPT,
                List.of(sidKey, oldAccessKey, keys.sessionByAccessToken(newAccess),
                        keys.sessionById(newSessionId), keys.sessionByRefreshToken(newRefresh)),
                Long.toString(APP_SESSION_TTL.getSeconds()), KIND_APP, newSessionId,
                accountId.toString(), nullToEmpty(installationId), Long.toString(snapshotRevision),
                Long.toString(now.toEpochMilli()), Long.toString(expiresAt.toEpochMilli()),
                StateKeys.sha256Hex(newAccess), StateKeys.sha256Hex(newRefresh)));
        return Optional.of(new IssuedAppSession(newAccess, newRefresh, accountId, installationId,
                expiresAt));
    }

    @Override
    public Optional<RevokedSession> revokeSession(String accessToken) {
        if (accessToken == null || accessToken.isBlank()) {
            return Optional.empty();
        }
        String accessKey = keys.sessionByAccessToken(accessToken);
        @SuppressWarnings("rawtypes")
        List raw = RedisFailures.call("revoke-session", () -> template.execute(REVOKE_SCRIPT,
                List.of(accessKey, sidNamespace(), refreshNamespace())));
        if (raw == null || raw.isEmpty()) {
            return Optional.empty();
        }
        String sessionId = raw.size() > 0 ? nullToEmpty(String.valueOf(raw.get(0))) : "";
        if (sessionId.isEmpty()) {
            return Optional.empty();
        }
        String kind = raw.size() > 1 ? nullToEmpty(String.valueOf(raw.get(1))) : "";
        String aid = raw.size() > 2 ? nullToEmpty(String.valueOf(raw.get(2))) : "";
        String iid = raw.size() > 3 ? nullToEmpty(String.valueOf(raw.get(3))) : "";
        if (KIND_GIMBAL.equals(kind)) {
            return Optional.of(new RevokedSession(null, null, sessionId));
        }
        return Optional.of(new RevokedSession(UUID.fromString(aid), emptyToNull(iid), sessionId));
    }

    @Override
    public IssuedGimbalSession createGimbalSession(UUID gimbalId, long credentialVersion) {
        Instant now = clock.instant();
        Instant expiresAt = now.plus(GIMBAL_SESSION_TTL);
        String access = randomToken();
        String sessionId = UUID.randomUUID().toString();
        String sidKey = keys.sessionById(sessionId);
        RedisFailures.call("create-gimbal-session", () -> template.execute(CREATE_SCRIPT,
                // KEYS[3] 在 hasRt=0 时不使用；用 sidKey 作占位具体键（绝不传命名空间）。
                List.of(keys.sessionByAccessToken(access), sidKey, sidKey),
                Long.toString(GIMBAL_SESSION_TTL.getSeconds()), KIND_GIMBAL, sessionId,
                gimbalId.toString(), "", Long.toString(credentialVersion),
                Long.toString(now.toEpochMilli()), Long.toString(expiresAt.toEpochMilli()),
                StateKeys.sha256Hex(access), "", "0"));
        return new IssuedGimbalSession(access, gimbalId, credentialVersion, expiresAt);
    }

    // ---------- internals ----------

    /** 与 {@code InMemorySessionDouble} 同一 SQL/口径；jdbc 为 null 时跳过（纯装配/一致性测试）。 */
    private boolean stillSameGeneration(UUID accountId, long snapshotRevision) {
        if (jdbc == null) {
            return true;
        }
        List<Object[]> rows = jdbc.query(
                "SELECT status, auth_revision FROM accounts WHERE id = ?",
                (rs, i) -> new Object[]{rs.getString("status"), rs.getLong("auth_revision")},
                accountId);
        return !rows.isEmpty()
                && "active".equals(rows.get(0)[0])
                && ((Long) rows.get(0)[1]).longValue() == snapshotRevision;
    }

    /**
     * 仅 {@code session-revoke.lua} 仍需要命名空间：被删的 sid/rt 键名来自脚本内 {@code HGETALL}
     * 的运行期结果，调用方执行前无法知道，而"读取+删除"必须原子。standalone 正确；cluster 迁移路径
     * 见类级 javadoc 与 {@code session-revoke.lua} 头部。
     */
    private String sidNamespace() {
        return keys.pattern("sess:sid:");
    }

    private String refreshNamespace() {
        return keys.pattern("sess:rt:");
    }

    private String randomToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static long parseLong(String value, long fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException malformed) {
            return fallback;
        }
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private static String emptyToNull(String value) {
        return value == null || value.isEmpty() ? null : value;
    }

    private static <T> DefaultRedisScript<T> script(String classpath, Class<T> resultType) {
        DefaultRedisScript<T> script = new DefaultRedisScript<>();
        script.setLocation(new ClassPathResource(classpath));
        script.setResultType(resultType);
        return script;
    }
}

package cn.yuanxin.mvp.web.testdouble;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.auth.SessionProvider;

import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 会话提供方测试替身（仅 dev/test，profile 隔离）。
 *
 * <p>不透明随机 token 绑定到本替身<b>自己签发</b>的会话数据；
 * authenticate() 只认自己签发且未过期/未撤销的 token——任何外部字符串
 * （包括拼出来的 accountId/installationId）绝不认证成功（fail closed）。
 * 无 PG 会话表（14 表设计不含；真实提供方未选定，见 digest gap 2）。</p>
 *
 * <p>会话快照携带签发时刻的 accounts.auth_revision（经 jdbc 单行读取）；
 * refresh 直读 T14 行：账号 disabled/行不存在 → empty（控制器映射
 * 401 SESSION_INVALID）。每请求与本地状态的复核在 PrincipalRevalidator。</p>
 */
public class InMemorySessionDouble implements SessionProvider {

    /** jdbc 可为 null（仅用于纯 bean 装配测试，如 ProductionFailClosedTest）。 */
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;

    public InMemorySessionDouble() {
        this(null);
    }

    public InMemorySessionDouble(org.springframework.jdbc.core.JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private record Session(String sessionId, PrincipalType type, UUID accountId,
                           String installationId, UUID gimbalId, long credentialVersion,
                           long authRevision, Instant expiresAt) {
        boolean alive() {
            return expiresAt.isAfter(Instant.now());
        }
    }

    private final Map<String, Session> byAccessToken = new ConcurrentHashMap<>();
    private final Map<String, String> refreshToSession = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();

    @Override
    public Optional<AuthenticatedPrincipal> authenticate(String accessToken) {
        Session s = byAccessToken.get(accessToken);
        if (s == null || !s.alive()) {
            return Optional.empty();
        }
        return Optional.of(toPrincipal(s));
    }

    @Override
    public IssuedAppSession createAppSession(UUID accountId, String installationId, long authRevision) {
        Session s = new Session(UUID.randomUUID().toString(), PrincipalType.APP, accountId,
                installationId, null, 0, authRevision, Instant.now().plus(Duration.ofHours(2)));
        String access = randomToken();
        String refresh = randomToken();
        byAccessToken.put(access, s);
        refreshToSession.put(refresh, s.sessionId());
        tokenBySession.put(s.sessionId(), access);
        refreshByToken.put(s.sessionId(), refresh);
        return new IssuedAppSession(access, refresh, accountId, installationId, s.expiresAt());
    }

    @Override
    public Optional<IssuedAppSession> refreshAppSession(String refreshCredential) {
        String sessionId = refreshToSession.remove(refreshCredential);
        if (sessionId == null) {
            return Optional.empty();
        }
        Session old = sessionById(sessionId);
        if (old == null || !old.alive()) {
            return Optional.empty();
        }
        // 刷新前复核本地账号状态并重新捕获 auth_revision（单行查询，无 JOIN）
        long authRevision = old.authRevision();
        if (jdbc != null) {
            List<long[]> snapshot = jdbc.query(
                    "SELECT auth_revision FROM accounts WHERE id = ? AND status = 'active'",
                    (rs, i) -> new long[]{rs.getLong("auth_revision")}, old.accountId());
            if (snapshot.isEmpty()) {
                revokeBySessionId(sessionId);   // 账号已 disabled：旧会话连带撤销
                return Optional.empty();
            }
            authRevision = snapshot.get(0)[0];
        }
        // 轮换：撤销旧 access token，签发新对
        revokeBySessionId(sessionId);
        return Optional.of(createAppSession(old.accountId(), old.installationId(), authRevision));
    }

    @Override
    public Optional<RevokedSession> revokeSession(String accessToken) {
        Session s = byAccessToken.remove(accessToken);
        if (s == null) {
            return Optional.empty();
        }
        String refresh = refreshByToken.remove(s.sessionId());
        if (refresh != null) {
            refreshToSession.remove(refresh);
        }
        tokenBySession.remove(s.sessionId());
        return Optional.of(new RevokedSession(s.accountId(), s.installationId(), s.sessionId()));
    }

    @Override
    public IssuedGimbalSession createGimbalSession(UUID gimbalId, long credentialVersion) {
        Session s = new Session(UUID.randomUUID().toString(), PrincipalType.GIMBAL, null,
                null, gimbalId, credentialVersion, 0, Instant.now().plus(Duration.ofHours(1)));
        String access = randomToken();
        byAccessToken.put(access, s);
        return new IssuedGimbalSession(access, gimbalId, credentialVersion, s.expiresAt());
    }

    /** 测试钩子：token → 会话 ID（= T09 session_ref），仅替身暴露。 */
    public String sessionIdForAccessToken(String accessToken) {
        Session s = byAccessToken.get(accessToken);
        return s == null ? null : s.sessionId();
    }

    // ---------- internals ----------

    private final Map<String, String> tokenBySession = new ConcurrentHashMap<>();
    private final Map<String, String> refreshByToken = new ConcurrentHashMap<>();

    private Session sessionById(String sessionId) {
        String token = tokenBySession.get(sessionId);
        return token == null ? null : byAccessToken.get(token);
    }

    private void revokeBySessionId(String sessionId) {
        String token = tokenBySession.remove(sessionId);
        if (token != null) {
            byAccessToken.remove(token);
        }
    }

    private static AuthenticatedPrincipal toPrincipal(Session s) {
        return s.type() == PrincipalType.APP
                ? AuthenticatedPrincipal.app(s.accountId(), s.installationId(), s.sessionId(),
                        s.authRevision())
                : AuthenticatedPrincipal.gimbal(s.gimbalId(), s.credentialVersion(), s.sessionId());
    }

    private String randomToken() {
        byte[] b = new byte[32];
        random.nextBytes(b);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(b);
    }
}

package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;

/**
 * {@link SessionProvider} 的<b>同一套契约测试</b>：对内存替身与 Redis 实现各跑一遍，
 * 防止两种后端实现漂移（Redis 子类为 opt-in，仅在提供真实 Redis 时运行）。
 *
 * <p>覆盖：authenticate 只认自己签发的 token；refresh 一次性；轮换后旧 access 立即失效；
 * revision 快照不符 ⇒ empty 且会话被撤销；账号非 active ⇒ 同上；revoke 恰好一次返回
 * {@code RevokedSession}；TTL（以 expiresAt 观测量）；云台 credentialVersion 快照。</p>
 */
abstract class SessionProviderContractTest {

    protected static final UUID ACCOUNT = UUID.fromString("00000000-0000-4000-8000-0000000000aa");
    protected static final UUID GIMBAL = UUID.fromString("00000000-0000-4000-8000-0000000000bb");
    protected static final long REVISION = 5L;

    protected JdbcTemplate jdbc;
    protected SessionProvider provider;

    /** 由具体后端创建 provider（jdbc 可为 mock）。 */
    protected abstract SessionProvider createProvider(JdbcTemplate jdbc);

    /** 每个测试后的后端清理钩子（Redis 子类清理自己前缀的键）。 */
    protected void cleanup() {
    }

    @BeforeEach
    void baseSetUp() {
        jdbc = mock(JdbcTemplate.class);
        stubAccount("active", REVISION);
        provider = createProvider(jdbc);
    }

    @AfterEach
    void baseTearDown() {
        cleanup();
    }

    @SuppressWarnings("unchecked")
    protected void stubAccount(String status, long revision) {
        lenient().when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(java.util.Collections.singletonList(new Object[]{status, revision}));
    }

    @SuppressWarnings("unchecked")
    protected void stubAccountMissing() {
        lenient().when(jdbc.query(anyString(), any(RowMapper.class), any()))
                .thenReturn(java.util.Collections.emptyList());
    }

    @Test
    @DisplayName("authenticate 只认自己签发的 token；任意字符串/空 token 恒 empty")
    void authenticateAcceptsOnlyOwnTokens() {
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-1", REVISION);
        assertThat(provider.authenticate(s.accessToken())).isPresent();
        assertThat(provider.authenticate("not-a-token")).isEmpty();
        assertThat(provider.authenticate("")).isEmpty();
    }

    @Test
    @DisplayName("APP 会话往返：快照字段正确、token 不透明、TTL≈2h")
    void appSessionRoundTripAndTtl() {
        Instant before = Instant.now();
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-1", REVISION);
        assertThat(s.accessToken()).isNotBlank();
        assertThat(s.refreshToken()).isNotBlank();
        assertThat(s.accessToken()).isNotEqualTo(s.refreshToken());
        assertThat(s.accountId()).isEqualTo(ACCOUNT);
        assertThat(s.installationId()).isEqualTo("inst-1");
        assertThat(s.expiresAt()).isBetween(before.plus(Duration.ofMinutes(110)),
                Instant.now().plus(Duration.ofMinutes(130)));

        AuthenticatedPrincipal p = provider.authenticate(s.accessToken()).orElseThrow();
        assertThat(p.principalType()).isEqualTo(PrincipalType.APP);
        assertThat(p.accountUuid()).isEqualTo(ACCOUNT);
        assertThat(p.installationId()).isEqualTo("inst-1");
        assertThat(p.sessionId()).isNotBlank();
        assertThat(p.authRevision()).isEqualTo(REVISION);
    }

    @Test
    @DisplayName("refresh 一次性：用一次即失效")
    void refreshIsSingleUse() {
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-1", REVISION);
        assertThat(provider.refreshAppSession(s.refreshToken())).isPresent();
        assertThat(provider.refreshAppSession(s.refreshToken())).isEmpty();
    }

    @Test
    @DisplayName("轮换令旧 access 立即失效；新 access 可用；沿用同一 revision 快照")
    void rotationInvalidatesOldAccessImmediately() {
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-1", REVISION);
        SessionProvider.IssuedAppSession rotated = provider.refreshAppSession(s.refreshToken()).orElseThrow();
        assertThat(rotated.accessToken()).isNotEqualTo(s.accessToken());
        assertThat(provider.authenticate(s.accessToken())).isEmpty();
        AuthenticatedPrincipal p = provider.authenticate(rotated.accessToken()).orElseThrow();
        assertThat(p.accountUuid()).isEqualTo(ACCOUNT);
        assertThat(p.installationId()).isEqualTo("inst-1");
        assertThat(p.authRevision()).as("沿用签发快照，绝不重捕获").isEqualTo(REVISION);
    }

    @Test
    @DisplayName("revision 快照不符 ⇒ empty 且会话被连带撤销（绝不复活旧代次）")
    void revisionMismatchRevokesSession() {
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-1", REVISION);
        stubAccount("active", REVISION + 1);
        assertThat(provider.refreshAppSession(s.refreshToken())).isEmpty();
        assertThat(provider.authenticate(s.accessToken()))
                .as("旧会话必须被撤销").isEmpty();
    }

    @Test
    @DisplayName("账号非 active ⇒ refresh empty 且会话被撤销")
    void disabledAccountRevokesSessionOnRefresh() {
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-1", REVISION);
        stubAccount("disabled", REVISION);
        assertThat(provider.refreshAppSession(s.refreshToken())).isEmpty();
        assertThat(provider.authenticate(s.accessToken())).isEmpty();
    }

    @Test
    @DisplayName("账号行缺失 ⇒ refresh empty 且会话被撤销")
    void missingAccountRevokesSessionOnRefresh() {
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-1", REVISION);
        stubAccountMissing();
        assertThat(provider.refreshAppSession(s.refreshToken())).isEmpty();
        assertThat(provider.authenticate(s.accessToken())).isEmpty();
    }

    @Test
    @DisplayName("revoke 恰好一次返回 RevokedSession，第二次 empty，且 access 失效")
    void revokeReturnsExactlyOnce() {
        SessionProvider.IssuedAppSession s = provider.createAppSession(ACCOUNT, "inst-1", REVISION);
        Optional<SessionProvider.RevokedSession> first = provider.revokeSession(s.accessToken());
        assertThat(first).isPresent();
        assertThat(first.get().accountId()).isEqualTo(ACCOUNT);
        assertThat(first.get().installationId()).isEqualTo("inst-1");
        assertThat(first.get().sessionId()).isNotBlank();
        assertThat(provider.revokeSession(s.accessToken())).isEmpty();
        assertThat(provider.authenticate(s.accessToken())).isEmpty();
    }

    @Test
    @DisplayName("云台会话：credentialVersion 快照、类型 GIMBAL、TTL≈1h，且无 refresh")
    void gimbalSessionSnapshotsCredentialVersion() {
        Instant before = Instant.now();
        SessionProvider.IssuedGimbalSession g = provider.createGimbalSession(GIMBAL, 42L);
        assertThat(g.sessionToken()).isNotBlank();
        assertThat(g.gimbalId()).isEqualTo(GIMBAL);
        assertThat(g.credentialVersion()).isEqualTo(42L);
        assertThat(g.expiresAt()).isBetween(before.plus(Duration.ofMinutes(50)),
                Instant.now().plus(Duration.ofMinutes(70)));

        AuthenticatedPrincipal p = provider.authenticate(g.sessionToken()).orElseThrow();
        assertThat(p.principalType()).isEqualTo(PrincipalType.GIMBAL);
        assertThat(p.gimbalUuid()).isEqualTo(GIMBAL);
        assertThat(p.credentialVersion()).isEqualTo(42L);
        assertThat(p.sessionId()).isNotBlank();
    }
}

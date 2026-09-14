package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.testdouble.SmsCodeDouble;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIf;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.env.Environment;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * <b>L3（root-only）真实 Redis 登录验收入口</b>：用真实 HTTP 驱动 真实 Redis 下的端到端登录闭环
 * （发码 → 核销建会话 → access 认证 → refresh 轮换（旧 access 立即 401）→ logout 撤销 + 复查 401），
 * 并按测试前缀 {@code SCAN} 证明确实使用 Redis（登录后有会话键、登出后消失）。
 *
 * <p><b>三重显式 opt-in（任一缺失即整类跳过）</b></p>
 * <ol>
 *   <li>{@code -DMVP_REDIS_LOGIN_LIVE=true}（或环境变量同名）——本类的 {@link EnabledIf} 门；</li>
 *   <li>真实 Redis 连接由<b>根</b>在命令行提供：
 *       {@code -Dspring.config.additional-location=file:<工作树外绝对路径>}
 *       或 {@code -Dspring.data.redis.host=... -Dspring.data.redis.port=...} 等。
 *       <b>本测试自身绝不读取、绝不打印私有配置文件内容</b>；</li>
 *   <li>{@code app.state.provider=redis}（由根的配置或命令行提供；测试在运行期断言其生效并需要
 *       {@link RedisSessionProvider} 被装配）。</li>
 * </ol>
 *
 * <p><b>短信：强制 doubles，本入口永不发送真实短信</b>。{@link DynamicPropertySource} <b>强制</b>
 * {@code app.sms.provider=doubles} 并显式设定 {@code app.testdouble.sms.fixed-code}，<b>不依赖任何默认值</b>；
 * 测试体内再运行期断言注入的 {@code SmsCodeProvider} 是 {@code SmsCodeDouble}，否则失败——
 * 这使 L3 <b>结构上不可能</b>向随机/真实手机号发送短信。真实短信联调属人工流程，
 * <b>不由本自动化入口覆盖</b>（若未来需要"真实短信 + 真实 Redis"的自动化，须另行设计并由根裁定）。</p>
 *
 * <p><b>隔离与清理</b>：用独立随机 {@code app.state.redis.key-prefix}（不覆盖/不清理根自有前缀的键），
 * 结束后只删自己前缀的键（绝不 FLUSHDB），并清理本测试新建的账号数据。</p>
 *
 * <p><b>根可直接复制的运行命令</b>（占位请替换为根的私有路径/端口；退出码非 0 即验收失败）：</p>
 * <pre>
 * MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55435/postgres \
 * MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=&lt;db-password&gt; \
 * mvn -f backend/web-java/pom.xml test -Dtest=RedisLoginLiveAcceptanceIT \
 *   -DMVP_REDIS_LOGIN_LIVE=true \
 *   -Dspring.config.additional-location=file:/abs/path/to/application-local.yml
 * </pre>
 *
 * <p>输出纪律：只打印键数量与布尔结果；<b>绝不</b>打印 token、验证码、手机号、完整键、Redis 主机或口令。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@EnabledIf("liveOptIn")
class RedisLoginLiveAcceptanceIT {

    static final String LIVE_FLAG = "MVP_REDIS_LOGIN_LIVE";

    /** 强制 doubles 时使用的固定验证码（测试显式设定，不依赖默认值）。 */
    private static final String FIXED_CODE = "123456";

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String KEY_PREFIX = "b-live-" + HexFormat.of().formatHex(randomBytes());

    static boolean liveOptIn() {
        String value = System.getProperty(LIVE_FLAG);
        if (value == null || value.isBlank()) {
            value = System.getenv(LIVE_FLAG);
        }
        return "true".equalsIgnoreCase(value == null ? "" : value.trim());
    }

    @BeforeAll
    static void requireRedisConnectionConfig() {
        assumeTrue(liveOptIn(), "set -D" + LIVE_FLAG + "=true to run the live login acceptance");
        assumeTrue(System.getProperty("spring.data.redis.host") != null
                        || System.getProperty("spring.data.redis.url") != null
                        || System.getProperty("spring.config.additional-location") != null,
                "provide real Redis via -Dspring.config.additional-location=file:<abs>"
                        + " or -Dspring.data.redis.*=...");
    }

    /**
     * 隔离键前缀，并<b>强制</b>短信走 doubles（不依赖默认值）：本入口永不发送真实短信。
     * 该覆盖在上下文创建前生效，故即使根的私有 YAML 配了 {@code app.sms.provider=aliyun}，
     * L3 也<b>结构上不可能</b>触发真实短信网关。
     */
    @DynamicPropertySource
    static void isolateKeyPrefixAndForceSmsDoubles(DynamicPropertyRegistry registry) {
        registry.add("app.state.redis.key-prefix", () -> KEY_PREFIX);
        registry.add("app.sms.provider", () -> "doubles");
        registry.add("app.testdouble.sms.fixed-code", () -> FIXED_CODE);
    }

    @Autowired
    private TestRestTemplate rest;

    @Autowired
    private StringRedisTemplate redis;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private Environment environment;

    @Autowired
    private SessionProvider sessionProvider;

    @Autowired
    private SmsCodeProvider smsCodeProvider;

    @Value("${app.testdouble.sms.fixed-code:" + FIXED_CODE + "}")
    private String fixedCode;

    @Test
    @DisplayName("真实 Redis 端到端登录：发码→建会话→认证→refresh（旧 access 401）→logout（复查 401）")
    void fullLoginLifecycleUsesRedis() throws Exception {
        assumeTrue("redis".equals(environment.getProperty("app.state.provider")),
                "L3 requires app.state.provider=redis from the root's private configuration");
        assertThat(sessionProvider).isInstanceOf(RedisSessionProvider.class);
        // 运行期硬断言：绝不因将来有人改掉 @DynamicPropertySource 的强制项而静默给真实号段发短信。
        assertThat(smsCodeProvider)
                .as("L3 must never send real SMS: SmsCodeProvider must be the doubles implementation")
                .isInstanceOf(SmsCodeDouble.class);

        String phone = "+86139" + String.format("%08d",
                Math.abs(RANDOM.nextLong() % 100_000_000L));
        String installationId = "live-inst-" + UUID.randomUUID().toString().substring(0, 8);
        try {
            // f01：发码
            ResponseEntity<String> challenge = postJson("/api/v1/auth/sms-challenges",
                    Map.of("phone", phone, "purpose", "login"), null);
            assertThat(challenge.getStatusCode().value()).isEqualTo(200);
            String challengeId = body(challenge).path("data").path("challengeId").asText();
            assertThat(challengeId).isNotBlank();

            // f02：核销建会话
            ResponseEntity<String> session = postJson("/api/v1/auth/sessions",
                    Map.of("challengeId", challengeId, "code", fixedCode,
                            "installationId", installationId), null);
            assertThat(session.getStatusCode().value()).isEqualTo(200);
            JsonNode sessionData = body(session).path("data");
            String access = sessionData.path("accessToken").asText();
            String refresh = sessionData.path("refreshToken").asText();
            assertThat(access).isNotBlank();
            assertThat(refresh).isNotBlank();

            // 证明确实用了 Redis：登录后存在本前缀的会话键（只报数量）。
            int keysAfterLogin = sessionKeys();
            assertThat(keysAfterLogin).as("session keys must exist after login").isPositive();

            // access 认证
            assertThat(getWithBearer("/api/v1/me/member-access-grants", access).getStatusCode().value())
                    .isEqualTo(200);

            // refresh 轮换：旧 access 立即 401，新 access 可用
            ResponseEntity<String> rotated = postJson("/api/v1/auth/session-refreshes",
                    Map.of("refreshCredential", refresh, "installationId", installationId), null);
            assertThat(rotated.getStatusCode().value()).isEqualTo(200);
            String newAccess = body(rotated).path("data").path("accessToken").asText();
            assertThat(newAccess).isNotBlank();
            assertThat(getWithBearer("/api/v1/me/member-access-grants", access).getStatusCode().value())
                    .as("old access must be invalid immediately after rotation").isEqualTo(401);
            assertThat(getWithBearer("/api/v1/me/member-access-grants", newAccess).getStatusCode().value())
                    .isEqualTo(200);

            // logout：204，随后 401
            HttpHeaders headers = new HttpHeaders();
            headers.setBearerAuth(newAccess);
            ResponseEntity<Void> revoked = rest.exchange("/api/v1/auth/sessions/current",
                    HttpMethod.DELETE, new HttpEntity<>(headers), Void.class);
            assertThat(revoked.getStatusCode().value()).isEqualTo(204);
            assertThat(getWithBearer("/api/v1/me/member-access-grants", newAccess).getStatusCode().value())
                    .isEqualTo(401);

            // 证明确实用了 Redis：登出后本前缀的会话键消失（只报数量）。
            assertThat(sessionKeys()).as("session keys must be gone after logout").isZero();
        } finally {
            cleanup(phone);
        }
    }

    // ---------- helpers ----------

    /** 用 {@code SCAN}（绝不用阻塞的 {@code KEYS}）统计本前缀的会话键数量。 */
    private int sessionKeys() {
        return RedisTestSupport.scanKeys(redis, KEY_PREFIX).size();
    }

    private ResponseEntity<String> postJson(String path, Map<String, Object> body, String access)
            throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        if (access != null) {
            headers.setBearerAuth(access);
        }
        return rest.postForEntity(path, new HttpEntity<>(JSON.writeValueAsString(body), headers),
                String.class);
    }

    private ResponseEntity<String> getWithBearer(String path, String access) {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(access);
        return rest.exchange(path, HttpMethod.GET, new HttpEntity<>(headers), String.class);
    }

    private static JsonNode body(ResponseEntity<String> response) throws Exception {
        return JSON.readTree(response.getBody());
    }

    /**
     * 清理本测试前缀的 Redis 键与本测试新建的账号数据。
     *
     * <p>Redis 侧：用 {@code SCAN}（绝不 {@code KEYS}）删除自己前缀，然后<b>复核</b>剩余键数为 0；
     * 清理异常或残留一律让测试失败（{@code cleanup incomplete}），绝不静默吞掉。</p>
     * <p>DB 侧：尽力而为，但必须报告删除行数（{@code >0} 与否）；异常以 suppressed 保留并在输出中
     * 标记 {@code cleanup incomplete}。<b>绝不</b>打印键名、手机号或 token。</p>
     */
    private void cleanup(String phone) {
        Throwable cleanupFailure = null;
        try {
            RedisTestSupport.cleanup(redis, KEY_PREFIX);
        } catch (RuntimeException failure) {
            cleanupFailure = failure;
        }
        int leftover;
        try {
            leftover = RedisTestSupport.scanKeys(redis, KEY_PREFIX).size();
        } catch (RuntimeException scanFailure) {
            if (cleanupFailure == null) {
                cleanupFailure = scanFailure;
            } else {
                cleanupFailure.addSuppressed(scanFailure);
            }
            leftover = -1;
        }
        if (leftover > 0 || leftover < 0) {
            IllegalStateException incomplete = new IllegalStateException(
                    "cleanup incomplete: leftover keys under test prefix = "
                            + (leftover < 0 ? "unverified" : leftover) + " (names not logged)");
            if (cleanupFailure != null) {
                incomplete.addSuppressed(cleanupFailure);
            }
            throw incomplete;
        }

        int destinationsDeleted = 0;
        int accountsDeleted = 0;
        try {
            destinationsDeleted = jdbc.update("DELETE FROM notification_destinations WHERE account_id IN"
                    + " (SELECT id FROM accounts WHERE login_provider = 'phone' AND login_subject = ?)",
                    phone);
            accountsDeleted = jdbc.update("DELETE FROM accounts WHERE login_provider = 'phone'"
                    + " AND login_subject = ?", phone);
        } catch (RuntimeException dbFailure) {
            if (cleanupFailure == null) {
                cleanupFailure = dbFailure;
            } else {
                cleanupFailure.addSuppressed(dbFailure);
            }
            System.out.println("[l3-cleanup] db-cleanup-error exception="
                    + dbFailure.getClass().getSimpleName());
        }
        System.out.println("[l3-cleanup] redisLeftover=" + leftover
                + " destinationsDeleted=" + destinationsDeleted
                + " accountsDeleted=" + accountsDeleted
                + (cleanupFailure == null ? ""
                        : " cleanup-incomplete-suppressed=" + cleanupFailure.getClass().getSimpleName()));
    }

    private static byte[] randomBytes() {
        byte[] bytes = new byte[6];
        RANDOM.nextBytes(bytes);
        return bytes;
    }
}

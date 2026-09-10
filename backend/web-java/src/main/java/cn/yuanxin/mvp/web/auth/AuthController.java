package cn.yuanxin.mvp.web.auth;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * 手机号会话认证基础协议（DD 4.1；x-foundation，不计入 27）。
 * 薄控制器：全部能力经端口（SmsCodeProvider / SessionProvider），
 * 本类只做校验、本地账号 find-or-create（T14）与信封投影。
 *
 * <p>不建会话存储表（14 表设计无 session 表）；token 不透明、只由提供方
 * 派生身份；请求体手机号不作为认证结果。退出：先撤会话，再按 session_ref
 * 条件失效 T09 目标（幂等补偿、字段级 UPDATE、只影响本次会话对应目标）。</p>
 */
@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private static final Logger log = LoggerFactory.getLogger(AuthController.class);
    private static final String LOGIN_PROVIDER = "phone";

    private final SmsCodeProvider smsCodeProvider;
    private final SessionProvider sessionProvider;
    private final JdbcTemplate jdbc;
    private final EnvelopeSupport envelopes;
    private final ObjectMapper objectMapper;

    public AuthController(SmsCodeProvider smsCodeProvider, SessionProvider sessionProvider,
                          JdbcTemplate jdbc, EnvelopeSupport envelopes, ObjectMapper objectMapper) {
        this.smsCodeProvider = smsCodeProvider;
        this.sessionProvider = sessionProvider;
        this.jdbc = jdbc;
        this.envelopes = envelopes;
        this.objectMapper = objectMapper;
    }

    // ---------- DTO（契约 additionalProperties:false → Jackson FAIL_ON_UNKNOWN 全局开启） ----------

    public record SmsChallengeRequest(
            @NotBlank @Pattern(regexp = "^\\+[1-9][0-9]{6,14}$",
                    message = "phone must be E.164") String phone,
            @NotBlank @Pattern(regexp = "^login$", message = "purpose must be login") String purpose) {
    }

    public record SmsChallengeData(String challengeId, int retryAfter) {
    }

    public record AppSessionRequestBody(
            @NotBlank String challengeId,
            @NotBlank @Size(max = 32) String code,
            @NotBlank @Size(max = 128) String installationId,
            Map<String, Object> installBindingMaterial) {
    }

    public record SessionRefreshRequestBody(
            @NotBlank String refreshCredential,
            @Size(max = 128) String installationId) {
    }

    public record AppSessionData(String accountId, String accessToken, String refreshToken,
                                 String tokenType, String expiresAt) {
    }

    // ---------- endpoints ----------

    @PostMapping("/sms-challenges")
    public SuccessEnvelope smsChallenge(@Valid @RequestBody SmsChallengeRequest body,
                                        HttpServletRequest request) {
        SmsCodeProvider.ChallengeOutcome outcome = smsCodeProvider.issue(body.phone(), body.purpose());
        return envelopes.ok(request, new SmsChallengeData(outcome.challengeId(),
                outcome.retryAfterSeconds()));
    }

    @PostMapping("/sessions")
    public SuccessEnvelope createSession(@Valid @RequestBody AppSessionRequestBody body,
                                         HttpServletRequest request) {
        String loginSubject = smsCodeProvider.verify(body.challengeId(), body.code())
                .orElseThrow(() -> new ApiException(ErrorCode.AUTH_REQUIRED,
                        "challenge or code invalid"));
        UUID accountId = findOrCreateAccount(loginSubject);
        SessionProvider.IssuedAppSession session =
                sessionProvider.createAppSession(accountId, body.installationId());
        return envelopes.ok(request, toAppSessionData(session));
    }

    @PostMapping("/session-refreshes")
    public SuccessEnvelope refresh(@Valid @RequestBody SessionRefreshRequestBody body,
                                   HttpServletRequest request) {
        SessionProvider.IssuedAppSession session = sessionProvider
                .refreshAppSession(body.refreshCredential())
                .orElseThrow(() -> new ApiException(ErrorCode.SESSION_INVALID,
                        "refresh credential invalid or rotated"));
        return envelopes.ok(request, toAppSessionData(session));
    }

    @DeleteMapping("/sessions/current")
    public ResponseEntity<Void> revokeCurrent(@RequestHeader("Authorization") String authorization,
                                              PrincipalContext principal,
                                              HttpServletRequest request) {
        String token = authorization.substring("Bearer ".length());
        SessionProvider.RevokedSession revoked = sessionProvider.revokeSession(token)
                .orElseThrow(() -> new ApiException(ErrorCode.SESSION_INVALID,
                        "session already revoked"));
        invalidateDestinations(revoked);
        return ResponseEntity.noContent().build();
    }

    // ---------- helpers ----------

    private AppSessionData toAppSessionData(SessionProvider.IssuedAppSession s) {
        return new AppSessionData(s.accountId().toString(), s.accessToken(), s.refreshToken(),
                "Bearer", EnvelopeSupport.rfc3339(s.expiresAt()));
    }

    /** (login_provider='phone', login_subject) 并发唯一映射（T14 UNIQUE）。 */
    private UUID findOrCreateAccount(String loginSubject) {
        Optional<UUID> existing = queryAccountId(loginSubject);
        if (existing.isPresent()) {
            touchLogin(existing.get());
            return existing.get();
        }
        UUID id = UUID.randomUUID();
        try {
            jdbc.update("INSERT INTO accounts (id, login_provider, login_subject, last_login_at)"
                            + " VALUES (?, ?, ?, now())",
                    id, LOGIN_PROVIDER, loginSubject);
            return id;
        } catch (DuplicateKeyException race) {
            return queryAccountId(loginSubject).orElseThrow(() ->
                    new ApiException(ErrorCode.INTERNAL, "account mapping race lost"));
        }
    }

    private Optional<UUID> queryAccountId(String loginSubject) {
        var rows = jdbc.query("SELECT id FROM accounts WHERE login_provider = ? AND login_subject = ?",
                (rs, i) -> rs.getObject("id", UUID.class), LOGIN_PROVIDER, loginSubject);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    private void touchLogin(UUID accountId) {
        jdbc.update("UPDATE accounts SET last_login_at = now(), updated_at = now() WHERE id = ?",
                accountId);
    }

    /** T09 会话目标失效：按 session_ref 条件更新（不得失效后来新登录的目标）。 */
    private void invalidateDestinations(SessionProvider.RevokedSession revoked) {
        try {
            int n = jdbc.update("UPDATE notification_destinations"
                            + " SET status = 'invalid', invalidated_at = now(), updated_at = now()"
                            + " WHERE session_ref = ? AND status = 'active'",
                    revoked.sessionId());
            log.info("revoked session invalidated {} notification destination(s) (installation={})",
                    n, revoked.installationId());
        } catch (RuntimeException e) {
            // 幂等补偿语义：撤销已生效；目标失效可后续补偿（DD 4.1），不反转登出
            log.warn("T09 invalidation failed for session_ref={} (compensable)",
                    revoked.sessionId(), e);
        }
    }
}

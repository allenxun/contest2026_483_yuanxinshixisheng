package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.devices.proof.PairingProofVerifier;
import cn.yuanxin.mvp.web.devices.proof.ProofFailure;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.BeginOutcome;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import cn.yuanxin.mvp.web.idempotency.IdempotencyHandle;
import cn.yuanxin.mvp.web.idempotency.IdempotencyService;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * M2-A06 绑定 / M2-A07 配网绑定状态 / M2-A08 解绑（DD L225-250）。
 *
 * <p>绑定竞争安全：{@code SELECT ... FOR UPDATE} 锁 T03 → 比对客户端预期
 * binding_revision → 字段级 UPDATE 带守卫；绝不覆盖他人绑定。同账号同代次
 * 重复绑定不写库、不递增代次；真实解绑递增 binding_revision，幂等空完成不递增。
 * 旧解绑（旧 If-Match）绝不删除他人后来的新绑定。</p>
 *
 * <p>解绑不撤销成员授权、不删报告/方案/记录、不改当前任务指针、不发停止指令
 * （本类只写 T03 的 bound_account_id/bound_at/binding_revision/updated_at）。</p>
 */
@Service
public class GimbalBindingService {

    public static final String OP_BIND = "m2-a06-bind-gimbal";
    public static final String OP_UNBIND = "m2-a08-unbind-gimbal";
    public static final String RESOURCE_TYPE = "gimbal_binding";
    public static final String NOT_VISIBLE_MESSAGE = "gimbal not visible";
    private static final String BINDING_CHANGED_MESSAGE = "gimbal binding revision changed";
    private static final String BOUND_TO_OTHER_MESSAGE = "gimbal is already bound to another account";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate txTemplate;
    private final IdempotencyService idempotencyService;
    private final PairingProofVerifier pairingProofVerifier;

    public GimbalBindingService(JdbcTemplate jdbc, TransactionTemplate txTemplate,
                                IdempotencyService idempotencyService,
                                PairingProofVerifier pairingProofVerifier) {
        this.jdbc = jdbc;
        this.txTemplate = txTemplate;
        this.idempotencyService = idempotencyService;
        this.pairingProofVerifier = pairingProofVerifier;
    }

    public record BindOutcome(DeviceDtos.BindingResultView view, boolean replayed) {
    }

    private record Row(UUID boundAccountId, long bindingRevision, Instant boundAt) {
    }

    private record BindTx(DeviceDtos.BindingResultView view, ApiException rejection) {
    }

    // ---------------- M2-A06 ----------------

    public BindOutcome bind(PrincipalContext principal, UUID gimbalId,
                            DeviceDtos.BindingBody body, String idempotencyKey) {
        requireApp(principal);
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "Idempotency-Key header is required");
        }
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("expectedBindingRevision", body.expectedBindingRevision());
        fields.put("pairingProof", body.pairingProof());
        fields.put("accountUuid", principal.accountUuid().toString());
        fields.put("installationId", principal.installationId());
        String payloadHash = CanonicalObjectBuilder.forOperation(OP_BIND)
                .pathParams(Map.of("gimbalId", gimbalId.toString()))
                .fields(fields).payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OP_BIND, idempotencyKey, payloadHash);
        return switch (outcome) {
            case BeginOutcome.ReplaySucceeded replay ->
                    new BindOutcome(projectReplay(principal, replay), true);
            case BeginOutcome.ReplayRejected rejected ->
                    throw IdempotencyService.replayedRejection(rejected);
            case BeginOutcome.NewAttempt fresh ->
                    new BindOutcome(bindFresh(principal, gimbalId, body, fresh.handle()), false);
        };
    }

    /** 重放按当前 T03 状态投影：期间已被他人绑定则 404，绝不谎报 self。 */
    private DeviceDtos.BindingResultView projectReplay(PrincipalContext principal,
                                                       BeginOutcome.ReplaySucceeded replay) {
        if (!RESOURCE_TYPE.equals(replay.resourceType()) || replay.resourceId() == null) {
            throw new ApiException(ErrorCode.INTERNAL, "unexpected replay resource");
        }
        Row row = load(replay.resourceId());
        if (row == null || !principal.accountUuid().equals(row.boundAccountId())) {
            throw notVisible();
        }
        return new DeviceDtos.BindingResultView("self", replay.resourceId().toString(),
                String.valueOf(row.bindingRevision()),
                row.boundAt() == null ? null : EnvelopeSupport.rfc3339(row.boundAt()));
    }

    private DeviceDtos.BindingResultView bindFresh(PrincipalContext principal, UUID gimbalId,
                                                   DeviceDtos.BindingBody body,
                                                   IdempotencyHandle handle) {
        ProofFailure failure = pairingProofVerifier.verify(body.pairingProof(), gimbalId,
                principal.accountUuid(), principal.installationId()).failure();
        if (failure != null) {
            rejectAndThrow(handle, proofError(failure));
        }
        long expected = parseBigint(body.expectedBindingRevision());
        BindTx tx = txTemplate.execute(status -> {
            Row row = loadForUpdate(gimbalId);
            if (row == null) {
                return rejected(handle, notVisible());
            }
            if (row.bindingRevision() != expected) {
                return rejected(handle, bindingChanged(row.bindingRevision()));
            }
            if (row.boundAccountId() == null) {
                List<Instant> bound = jdbc.query("UPDATE gimbals SET bound_account_id = ?,"
                                + " bound_at = now(), binding_revision = binding_revision + 1,"
                                + " updated_at = now()"
                                + " WHERE id = ? AND binding_revision = ? RETURNING bound_at",
                        (rs, i) -> rs.getTimestamp("bound_at").toInstant(),
                        principal.accountUuid(), gimbalId, row.bindingRevision());
                if (bound.isEmpty()) {
                    return rejected(handle, bindingChanged(row.bindingRevision()));
                }
                long revision = row.bindingRevision() + 1;
                idempotencyService.completeSuccess(handle, RESOURCE_TYPE, gimbalId,
                        bindingSummary(gimbalId, revision, bound.get(0)));
                return new BindTx(new DeviceDtos.BindingResultView("self", gimbalId.toString(),
                        String.valueOf(revision), EnvelopeSupport.rfc3339(bound.get(0))), null);
            }
            if (row.boundAccountId().equals(principal.accountUuid())) {
                // 同账号同代次重复绑定：不写库、不递增代次（SC-01-04）。
                idempotencyService.completeSuccess(handle, RESOURCE_TYPE, gimbalId,
                        bindingSummary(gimbalId, row.bindingRevision(), row.boundAt()));
                return new BindTx(new DeviceDtos.BindingResultView("self", gimbalId.toString(),
                        String.valueOf(row.bindingRevision()),
                        row.boundAt() == null ? null : EnvelopeSupport.rfc3339(row.boundAt())), null);
            }
            return rejected(handle, boundToOther());
        });
        if (tx.rejection() != null) {
            throw tx.rejection();
        }
        return tx.view();
    }

    // ---------------- M2-A07 ----------------

    public DeviceDtos.BindingStatusView bindingStatus(PrincipalContext principal, UUID gimbalId,
                                                      String pairingProof) {
        requireApp(principal);
        if (pairingProof == null || pairingProof.isBlank()) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "X-Pairing-Proof header is required");
        }
        ProofFailure failure = pairingProofVerifier.verify(pairingProof, gimbalId,
                principal.accountUuid(), principal.installationId()).failure();
        if (failure != null) {
            // A07 契约只声明 400（缺头）/403（验证失败），无"结构非法"分支：
            // 非空证明的任何验证失败统一 403。
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "pairingProof could not be verified for this gimbal and account");
        }
        Row row = load(gimbalId);
        if (row == null) {
            throw notVisible();
        }
        String bindingStatus = row.boundAccountId() == null ? "unbound"
                : row.boundAccountId().equals(principal.accountUuid()) ? "self" : "other";
        return new DeviceDtos.BindingStatusView(bindingStatus, String.valueOf(row.bindingRevision()));
    }

    // ---------------- M2-A08 ----------------

    public void unbind(PrincipalContext principal, UUID gimbalId, String ifMatch,
                       String idempotencyKey) {
        requireApp(principal);
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "Idempotency-Key header is required");
        }
        Long expected = parseIfMatch(ifMatch);

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("ifMatch", ifMatch);
        fields.put("accountUuid", principal.accountUuid().toString());
        fields.put("installationId", principal.installationId());
        String payloadHash = CanonicalObjectBuilder.forOperation(OP_UNBIND)
                .pathParams(Map.of("gimbalId", gimbalId.toString()))
                .fields(fields).payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OP_UNBIND, idempotencyKey, payloadHash);
        switch (outcome) {
            case BeginOutcome.ReplaySucceeded ignored -> {
                return; // 原解绑重放：仍 204
            }
            case BeginOutcome.ReplayRejected rejected ->
                    throw IdempotencyService.replayedRejection(rejected);
            case BeginOutcome.NewAttempt fresh -> unbindFresh(principal, gimbalId, expected,
                    fresh.handle());
        }
    }

    private void unbindFresh(PrincipalContext principal, UUID gimbalId, Long expected,
                             IdempotencyHandle handle) {
        ApiException rejection = txTemplate.execute(status -> {
            Row row = loadForUpdate(gimbalId);
            if (row == null) {
                return rejectInTx(handle, notVisible());
            }
            if (expected != null && expected.longValue() != row.bindingRevision()) {
                return rejectInTx(handle, bindingChanged(row.bindingRevision()));
            }
            if (row.boundAccountId() != null
                    && row.boundAccountId().equals(principal.accountUuid())) {
                List<Long> updated = jdbc.query("UPDATE gimbals SET bound_account_id = NULL,"
                                + " bound_at = NULL, binding_revision = binding_revision + 1,"
                                + " updated_at = now()"
                                + " WHERE id = ? AND bound_account_id = ? AND binding_revision = ?"
                                + " RETURNING binding_revision",
                        (rs, i) -> rs.getLong("binding_revision"),
                        gimbalId, principal.accountUuid(), row.bindingRevision());
                if (updated.isEmpty()) {
                    return rejectInTx(handle, bindingChanged(row.bindingRevision()));
                }
                idempotencyService.completeSuccess(handle, RESOURCE_TYPE, gimbalId,
                        Map.of("gimbalId", gimbalId.toString(), "bindingStatus", "unbound",
                                "bindingRevision", String.valueOf(updated.get(0))));
                return null;
            }
            if (row.boundAccountId() == null) {
                // 已解除且未被重新绑定：幂等完成，不递增代次、不改任何列。
                idempotencyService.completeSuccess(handle, RESOURCE_TYPE, gimbalId,
                        Map.of("gimbalId", gimbalId.toString(), "bindingStatus", "unbound",
                                "bindingRevision", String.valueOf(row.bindingRevision())));
                return null;
            }
            // 他人绑定：带相符 If-Match（说明是他人新绑定）→ BINDING_CHANGED；否则 404，
            // 不泄漏"已被他人绑定"这一事实，绝不解除他人绑定。
            return rejectInTx(handle, expected != null && expected.longValue() == row.bindingRevision()
                    ? bindingChanged(row.bindingRevision()) : notVisible());
        });
        if (rejection != null) {
            throw rejection;
        }
    }

    // ---------------- shared ----------------

    private Row load(UUID gimbalId) {
        List<Row> rows = jdbc.query("SELECT bound_account_id, binding_revision, bound_at"
                        + " FROM gimbals WHERE id = ?",
                (rs, i) -> new Row(rs.getObject("bound_account_id", UUID.class),
                        rs.getLong("binding_revision"),
                        rs.getTimestamp("bound_at") == null ? null
                                : rs.getTimestamp("bound_at").toInstant()),
                gimbalId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Row loadForUpdate(UUID gimbalId) {
        List<Row> rows = jdbc.query("SELECT bound_account_id, binding_revision, bound_at"
                        + " FROM gimbals WHERE id = ? FOR UPDATE",
                (rs, i) -> new Row(rs.getObject("bound_account_id", UUID.class),
                        rs.getLong("binding_revision"),
                        rs.getTimestamp("bound_at") == null ? null
                                : rs.getTimestamp("bound_at").toInstant()),
                gimbalId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private BindTx rejected(IdempotencyHandle handle, ApiException error) {
        return new BindTx(null, rejectInTx(handle, error));
    }

    private ApiException rejectInTx(IdempotencyHandle handle, ApiException error) {
        idempotencyService.completeRejected(handle, error.getCode(), error.getHttpStatus(),
                error.getMessage(), error.isRetryable(), error.getDetails());
        return error;
    }

    private void rejectAndThrow(IdempotencyHandle handle, ApiException error) {
        txTemplate.execute(status -> {
            idempotencyService.completeRejected(handle, error.getCode(), error.getHttpStatus(),
                    error.getMessage(), error.isRetryable(), error.getDetails());
            return null;
        });
        throw error;
    }

    private static Map<String, Object> bindingSummary(UUID gimbalId, long revision,
                                                      Instant boundAt) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("gimbalId", gimbalId.toString());
        summary.put("bindingStatus", "self");
        summary.put("bindingRevision", String.valueOf(revision));
        summary.put("boundAt", boundAt == null ? null : EnvelopeSupport.rfc3339(boundAt));
        return summary;
    }

    private static ApiException proofError(ProofFailure failure) {
        return switch (failure) {
            case MISSING, MALFORMED -> new ApiException(ErrorCode.INVALID_INPUT,
                    "pairingProof is missing or malformed");
            default -> new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "pairingProof could not be verified for this gimbal and account");
        };
    }

    private static Long parseIfMatch(String ifMatch) {
        if (ifMatch == null || ifMatch.isBlank()) {
            return null;
        }
        String value = ifMatch.trim();
        if (value.length() >= 2 && value.startsWith("\"") && value.endsWith("\"")) {
            value = value.substring(1, value.length() - 1);
        }
        if (!value.startsWith("binding-")) {
            throw new ApiException(ErrorCode.INVALID_INPUT,
                    "If-Match must be \"binding-{bindingRevision}\"");
        }
        String revision = value.substring("binding-".length());
        if (!revision.matches("^(0|[1-9][0-9]*)$")) {
            throw new ApiException(ErrorCode.INVALID_INPUT,
                    "If-Match binding revision must be an unsigned decimal bigint string");
        }
        try {
            return Long.parseLong(revision);
        } catch (NumberFormatException e) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "If-Match binding revision overflow");
        }
    }

    private static long parseBigint(String value) {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException e) {
            throw new ApiException(ErrorCode.INVALID_INPUT,
                    "expectedBindingRevision out of bigint range");
        }
    }

    private static ApiException bindingChanged(long currentRevision) {
        return new ApiException(ErrorCode.BINDING_CHANGED, 409, BINDING_CHANGED_MESSAGE,
                Map.of("currentBindingRevision", String.valueOf(currentRevision)), Map.of());
    }

    private static ApiException boundToOther() {
        return new ApiException(ErrorCode.BOUND_TO_OTHER, 409, BOUND_TO_OTHER_MESSAGE, null, Map.of());
    }

    private static void requireApp(PrincipalContext principal) {
        if (principal.principalType() != PrincipalType.APP) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "this endpoint is only available to app account sessions");
        }
    }

    private static ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, NOT_VISIBLE_MESSAGE);
    }
}

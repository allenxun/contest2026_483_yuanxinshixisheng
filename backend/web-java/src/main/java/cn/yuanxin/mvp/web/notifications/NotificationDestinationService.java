package cn.yuanxin.mvp.web.notifications;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.BeginOutcome;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import cn.yuanxin.mvp.web.idempotency.IdempotencyHandle;
import cn.yuanxin.mvp.web.idempotency.IdempotencyService;
import cn.yuanxin.mvp.web.idempotency.Jcs;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * M5-A01 目标登记业务（DD M5-A01；lane-m5 第一部分）。
 *
 * <p>每条目标落在 T09 {@code notification_destinations}（installation_id 唯一）。
 * 事务内先 {@code SELECT ... FOR UPDATE}，再按"行不存在 / 同账号 / 换号"三分支
 * 做<b>字段级</b>写入；首建并发用
 * {@code INSERT ... ON CONFLICT (installation_id) DO NOTHING} 去重（不靠捕获
 * 异常导致事务 abort）。</p>
 *
 * <p><b>代次/换号语义</b>：内容变化、换号接管，以及相同内容但会话引用变化
 * （含 {@code invalid} 行重新激活）都 {@code destination_revision + 1}，使旧
 * 会话目标的 T10 通知路由快照全部失配并取消；仅"同会话且已 {@code active}"
 * 的纯幂等重登记不递增代次。若登出侧 {@code invalid} 失效不改代次，重新激活
 * 仍会由本服务 +1，故旧 revision 不被复用。
 * {@code expectedDestinationRevision} 不符复用 409 {@code BINDING_CHANGED}
 * ——契约无"目标代次不符"专用码且 B 不得新增错误码；DD 3.2 该码语义正是
 * "刷新当前状态并重新操作；旧请求不得改写新事实"，details 只含
 * {@code currentDestinationRevision}（不泄漏其他账号信息）。</p>
 */
@Service
public class NotificationDestinationService {

    /** 契约固定 operation（canonicalObject 首键）。 */
    public static final String OPERATION = "m5-a01-register-notification-destination";

    private static final String RESOURCE_TYPE = "notification_destination";

    private static final String SELECT_FOR_UPDATE =
            "SELECT id, account_id, destination_revision, provider, platform,"
                    + " registration::text AS registration, status, session_ref"
                    + " FROM notification_destinations WHERE installation_id = ? FOR UPDATE";

    private static final String SELECT_BY_ID =
            "SELECT id, account_id, destination_revision, status"
                    + " FROM notification_destinations WHERE id = ?";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate txTemplate;
    private final IdempotencyService idempotencyService;
    private final ObjectMapper objectMapper;

    public NotificationDestinationService(JdbcTemplate jdbc, TransactionTemplate txTemplate,
                                          IdempotencyService idempotencyService,
                                          ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.txTemplate = txTemplate;
        this.idempotencyService = idempotencyService;
        this.objectMapper = objectMapper;
    }

    /** 登记结果：响应投影 + 是否 T13 重放。 */
    public record RegisterResult(String destinationId, String destinationRevision,
                                 String status, boolean replayed) {
    }

    /** 业务事务返回：成功投影，或需在提交后抛出的确定性拒绝。 */
    private record TxOutcome(RegisterResult result, ApiException rejection) {
    }

    /** T09 行快照（FOR UPDATE 读）。 */
    private record DestinationRow(UUID id, UUID accountId, long revision, String provider,
                                  String platform, String registrationText, String status,
                                  String sessionRef) {
    }

    public RegisterResult register(PrincipalContext principal, String installationId,
                                   NotificationDestinationDtos.Request body, String idempotencyKey) {
        Map<String, Object> effectiveRegistration = normalizeRegistration(body.registration());
        String payloadHash = canonicalHash(principal, installationId, body, effectiveRegistration);

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OPERATION, idempotencyKey, payloadHash);
        IdempotencyHandle handle;
        switch (outcome) {
            case BeginOutcome.ReplaySucceeded replay -> {
                return projectReplay(replay, principal);
            }
            case BeginOutcome.ReplayRejected rejected ->
                    throw IdempotencyService.replayedRejection(rejected);
            case BeginOutcome.NewAttempt fresh -> handle = fresh.handle();
        }

        TxOutcome txOutcome = txTemplate.execute(status ->
                applyRegistration(handle, principal, installationId, body, effectiveRegistration));
        if (txOutcome == null) {
            throw new ApiException(ErrorCode.INTERNAL, "registration transaction returned no outcome");
        }
        if (txOutcome.rejection() != null) {
            throw txOutcome.rejection();
        }
        return txOutcome.result();
    }

    // ---------------- transactional core ----------------

    private TxOutcome applyRegistration(IdempotencyHandle handle, PrincipalContext principal,
                                        String installationId, NotificationDestinationDtos.Request body,
                                        Map<String, Object> effectiveRegistration) {
        List<DestinationRow> rows = jdbc.query(SELECT_FOR_UPDATE,
                (rs, i) -> new DestinationRow(
                        rs.getObject("id", UUID.class),
                        rs.getObject("account_id", UUID.class),
                        rs.getLong("destination_revision"),
                        rs.getString("provider"),
                        rs.getString("platform"),
                        rs.getString("registration"),
                        rs.getString("status"),
                        rs.getString("session_ref")),
                installationId);

        if (rows.isEmpty()) {
            if (!"0".equals(body.expectedDestinationRevision())) {
                return reject(handle, currentRevisionDetails(0L));
            }
            UUID destinationId = UUID.randomUUID();
            int inserted = jdbc.update("INSERT INTO notification_destinations"
                            + " (id, installation_id, account_id, destination_revision, provider,"
                            + " platform, registration, status, session_ref, last_registered_at,"
                            + " invalidated_at)"
                            + " VALUES (?, ?, ?, 1, ?, ?, ?::jsonb, 'active', ?, now(), NULL)"
                            + " ON CONFLICT (installation_id) DO NOTHING",
                    destinationId, installationId, principal.accountUuid(), body.provider(),
                    body.platform(), writeJson(effectiveRegistration), principal.sessionId());
            if (inserted == 1) {
                idempotencyService.completeSuccess(handle, RESOURCE_TYPE, destinationId,
                        Map.of("destinationId", destinationId.toString(),
                                "destinationRevision", "1", "status", "active"));
                return ok(destinationId, 1L, "active");
            }
            // 并发首建落败：改走"行已存在"分支（不 500）。
            rows = jdbc.query(SELECT_FOR_UPDATE,
                    (rs, i) -> new DestinationRow(
                            rs.getObject("id", UUID.class),
                            rs.getObject("account_id", UUID.class),
                            rs.getLong("destination_revision"),
                            rs.getString("provider"), rs.getString("platform"),
                            rs.getString("registration"), rs.getString("status"),
                            rs.getString("session_ref")),
                    installationId);
            if (rows.isEmpty()) {
                throw new ApiException(ErrorCode.INTERNAL, "destination conflict resolution lost row");
            }
        }

        DestinationRow row = rows.get(0);
        if (row.accountId() != null && row.accountId().equals(principal.accountUuid())) {
            return sameAccount(handle, principal, body, effectiveRegistration, row);
        }
        return accountSwitch(handle, principal, body, effectiveRegistration, row);
    }

    private TxOutcome sameAccount(IdempotencyHandle handle, PrincipalContext principal,
                                  NotificationDestinationDtos.Request body,
                                  Map<String, Object> effectiveRegistration, DestinationRow row) {
        if (!body.expectedDestinationRevision().equals(String.valueOf(row.revision()))) {
            return reject(handle, currentRevisionDetails(row.revision()));
        }
        boolean sameContent = body.provider().equals(row.provider())
                && body.platform().equals(row.platform())
                && canonicalJson(effectiveRegistration).equals(canonicalOfText(row.registrationText()));
        if (sameContent) {
            boolean pureIdempotent = Objects.equals(principal.sessionId(), row.sessionRef())
                    && "active".equals(row.status());
            if (pureIdempotent) {
                // 纯幂等重登记：会话未变且已 active → 不递增代次，仅刷新登记时间。
                jdbc.update("UPDATE notification_destinations"
                                + " SET last_registered_at = now(), updated_at = now()"
                                + " WHERE id = ?",
                        row.id());
                idempotencyService.completeSuccess(handle, RESOURCE_TYPE, row.id(),
                        summary(row.id(), row.revision(), "active"));
                return ok(row.id(), row.revision(), "active");
            }
            // 会话引用变化 / invalid 重新激活：安全相关变更必须递增代次，
            // 使 T10 记录的旧 revision 失配、旧通知被取消（裁定第 4 项）。
            int updated = jdbc.update("UPDATE notification_destinations"
                            + " SET session_ref = ?, last_registered_at = now(), status = 'active',"
                            + " invalidated_at = NULL, destination_revision = destination_revision + 1,"
                            + " updated_at = now()"
                            + " WHERE id = ? AND destination_revision = ?",
                    principal.sessionId(), row.id(), row.revision());
            if (updated == 0) {
                throw ApiException.requestInProgress(1);
            }
            long nextRevision = row.revision() + 1;
            idempotencyService.completeSuccess(handle, RESOURCE_TYPE, row.id(),
                    summary(row.id(), nextRevision, "active"));
            return ok(row.id(), nextRevision, "active");
        }
        int updated = jdbc.update("UPDATE notification_destinations"
                        + " SET provider = ?, platform = ?, registration = ?::jsonb, session_ref = ?,"
                        + " last_registered_at = now(), status = 'active', invalidated_at = NULL,"
                        + " destination_revision = destination_revision + 1, updated_at = now()"
                        + " WHERE id = ? AND destination_revision = ?",
                body.provider(), body.platform(), writeJson(effectiveRegistration),
                principal.sessionId(), row.id(), row.revision());
        if (updated == 0) {
            throw ApiException.requestInProgress(1);
        }
        long nextRevision = row.revision() + 1;
        idempotencyService.completeSuccess(handle, RESOURCE_TYPE, row.id(),
                summary(row.id(), nextRevision, "active"));
        return ok(row.id(), nextRevision, "active");
    }

    /**
     * 换号接管（SC-01-17）：调用方用 token 证明了对该安装实例的控制
     * （installationId 来自 token），允许接管。契约没有 GET 目标端点，
     * 换号方读不到当前代次，因此接受 {@code "0"} 或当前值；随后
     * {@code destination_revision + 1} 使旧账号快照全部失效。
     */
    private TxOutcome accountSwitch(IdempotencyHandle handle, PrincipalContext principal,
                                    NotificationDestinationDtos.Request body,
                                    Map<String, Object> effectiveRegistration, DestinationRow row) {
        String expected = body.expectedDestinationRevision();
        if (!"0".equals(expected) && !expected.equals(String.valueOf(row.revision()))) {
            return reject(handle, currentRevisionDetails(row.revision()));
        }
        int updated = jdbc.update("UPDATE notification_destinations"
                        + " SET account_id = ?, session_ref = ?, provider = ?, platform = ?,"
                        + " registration = ?::jsonb, status = 'active', invalidated_at = NULL,"
                        + " last_registered_at = now(), destination_revision = destination_revision + 1,"
                        + " updated_at = now()"
                        + " WHERE id = ? AND destination_revision = ?",
                principal.accountUuid(), principal.sessionId(), body.provider(), body.platform(),
                writeJson(effectiveRegistration), row.id(), row.revision());
        if (updated == 0) {
            throw ApiException.requestInProgress(1);
        }
        long nextRevision = row.revision() + 1;
        idempotencyService.completeSuccess(handle, RESOURCE_TYPE, row.id(),
                summary(row.id(), nextRevision, "active"));
        return ok(row.id(), nextRevision, "active");
    }

    // ---------------- replay ----------------

    /**
     * T13 重放：只定位原资源并按当前 T09 状态投影，不重做写入。若该行当前已
     * 归属其他账号（安装实例被接管），视为对当前主体不可见 → 同一 404
     * RESOURCE_NOT_VISIBLE（不泄漏存在性）。
     */
    private RegisterResult projectReplay(BeginOutcome.ReplaySucceeded replay,
                                         PrincipalContext principal) {
        if (!RESOURCE_TYPE.equals(replay.resourceType()) || replay.resourceId() == null) {
            throw new ApiException(ErrorCode.INTERNAL, "unexpected replay resource");
        }
        List<DestinationRow> rows = jdbc.query(SELECT_BY_ID,
                (rs, i) -> new DestinationRow(rs.getObject("id", UUID.class),
                        rs.getObject("account_id", UUID.class), rs.getLong("destination_revision"),
                        null, null, null, rs.getString("status"), null),
                replay.resourceId());
        if (rows.isEmpty() || rows.get(0).accountId() == null
                || !rows.get(0).accountId().equals(principal.accountUuid())) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, "destination not visible");
        }
        DestinationRow row = rows.get(0);
        return new RegisterResult(row.id().toString(), String.valueOf(row.revision()),
                row.status(), true);
    }

    // ---------------- helpers ----------------

    /**
     * 注册资料规范化：空对象 → 400（active 行要求非空注册）；缺
     * {@code schema_version} 时服务端注入整数 1；显式给出但非 JSON 整数 →
     * 400（不静默改写，也避免 DB CHECK 直接报错）。
     */
    static Map<String, Object> normalizeRegistration(Map<String, Object> raw) {
        Map<String, Object> copy = new LinkedHashMap<>(raw);
        if (copy.isEmpty()) {
            throw invalidInput("registration must be a non-empty object");
        }
        Object version = copy.get("schema_version");
        if (version == null) {
            copy.put("schema_version", 1);
            return copy;
        }
        if (!isIntegralJsonNumber(version)) {
            throw invalidInput("registration.schema_version must be a JSON integer");
        }
        return copy;
    }

    private static boolean isIntegralJsonNumber(Object value) {
        return value instanceof Integer || value instanceof Long || value instanceof Short
                || value instanceof Byte || value instanceof java.math.BigInteger;
    }

    private static ApiException invalidInput(String message) {
        return new ApiException(ErrorCode.INVALID_INPUT, message);
    }

    private static Map<String, Object> currentRevisionDetails(long revision) {
        return Map.of("currentDestinationRevision", String.valueOf(revision));
    }

    private TxOutcome reject(IdempotencyHandle handle, Map<String, Object> details) {
        idempotencyService.completeRejected(handle, ErrorCode.BINDING_CHANGED,
                ErrorCode.BINDING_CHANGED.defaultStatus().value(),
                "destination revision changed; refresh current state and retry", false, details);
        return new TxOutcome(null, new ApiException(ErrorCode.BINDING_CHANGED,
                "destination revision changed; refresh current state and retry", details));
    }

    private static TxOutcome ok(UUID id, long revision, String status) {
        return new TxOutcome(new RegisterResult(id.toString(), String.valueOf(revision),
                status, false), null);
    }

    private static Map<String, Object> summary(UUID id, long revision, String status) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("destinationId", id.toString());
        map.put("destinationRevision", String.valueOf(revision));
        map.put("status", status);
        return map;
    }

    private String canonicalHash(PrincipalContext principal, String installationId,
                                 NotificationDestinationDtos.Request body,
                                 Map<String, Object> effectiveRegistration) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("provider", body.provider());
        fields.put("platform", body.platform());
        fields.put("registration", effectiveRegistration);
        fields.put("expectedDestinationRevision", body.expectedDestinationRevision());
        fields.put("accountId", principal.accountUuid().toString());
        fields.put("installationId", installationId);
        return CanonicalObjectBuilder.forOperation(OPERATION)
                .pathParams(Map.of("installationId", installationId))
                .fields(fields)
                .payloadHash();
    }

    private static String canonicalJson(Map<String, Object> value) {
        return Jcs.canonicalize(Jcs.toNode(value));
    }

    private static String canonicalOfText(String jsonbText) {
        return Jcs.canonicalize(Jcs.parseStrict(jsonbText));
    }

    private String writeJson(Map<String, Object> value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw invalidInput("registration is not JSON-serializable");
        }
    }
}

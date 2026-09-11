package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.BeginOutcome;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import cn.yuanxin.mvp.web.idempotency.IdempotencyHandle;
import cn.yuanxin.mvp.web.idempotency.IdempotencyService;
import cn.yuanxin.mvp.web.devices.proof.ConnectionProofVerifier;
import cn.yuanxin.mvp.web.devices.proof.ProofFailure;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * M2-A04 微晶观察登记 / M2-A05 能力读取（DD L207-223）。
 *
 * <p>先校验 {@code connectionProof}（B 自有端口 + 替身；控制端归属由认证主体
 * 派生，请求体不得覆盖），再单表定位/登记 T04 并锁行判序（真实
 * observation_epoch/observation_seq 列，直接写列不塞 JSONB）。顺序权威是服务端
 * 维护的会话代次表（{@link ObservationSessions}，Oracle 第二轮 #2），写进
 * {@code latest_observation} JSONB 的 {@code observer_sessions}/
 * {@code observer_generation}/{@code observer_credential_version} 键。来源变化
 * （observer_type/observer_ref 不同）重置并重新从 generation=1 开始；来源相同则按
 * 服务端会话次序判定：只有 generation 更大才接受并重置，同 generation 内客户端
 * 不得更换 epoch 且 seq 必须严格更大，旧 generation 一律拒绝（旧会话永不重获
 * 权威，闭合两会话交替来回覆盖）。所有 accepted=false 都不覆盖能力。客户端自填
 * epoch 绝不作为新旧权威。</p>
 *
 * <p>禁止：以观察抢占/改变 T07 占用、累计次数、改 care_executions、创建
 * async_jobs（方案生成归 D/C 的 Worker 扫描）；不得用请求体覆盖他人归属。
 * 响应 {@code capabilityRevision} = 当前已登记 capabilities.revision。</p>
 *
 * <p>幂等顺序：认证 → T13 begin（重放短路）→ 证明校验 → 业务事务。这既满足
 * "先鉴权再 begin"（公约 §2），又保证同键同内容重放无需再次消耗 proof nonce。</p>
 */
@Service
public class MicrocrystalService {

    private static final Logger log = LoggerFactory.getLogger(MicrocrystalService.class);

    public static final String OP_OBSERVE = "m2-a04-microcrystal-observation";
    public static final String RESOURCE_TYPE = "microcrystal";
    public static final String NOT_VISIBLE_MESSAGE = "microcrystal not visible";
    private static final String BIGINT = "^(0|[1-9][0-9]*)$";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate txTemplate;
    private final IdempotencyService idempotencyService;
    private final ConnectionProofVerifier connectionProofVerifier;
    private final DeviceProperties props;

    public MicrocrystalService(JdbcTemplate jdbc, TransactionTemplate txTemplate,
                               IdempotencyService idempotencyService,
                               ConnectionProofVerifier connectionProofVerifier,
                               DeviceProperties props) {
        this.jdbc = jdbc;
        this.txTemplate = txTemplate;
        this.idempotencyService = idempotencyService;
        this.connectionProofVerifier = connectionProofVerifier;
        this.props = props;
    }

    public record ObservationOutcome(DeviceDtos.MicrocrystalObservationAck ack, boolean replayed) {
    }

    private record Observer(String type, String ref) {
    }

    private record Row(String observerType, String observerRef, String observationEpoch,
                       Long observationSeq, String capabilities, Instant receivedAt,
                       String latestObservation) {
    }

    // ---------------- M2-A04 ----------------

    public ObservationOutcome report(PrincipalContext principal,
                                     DeviceDtos.MicrocrystalObservationBody body,
                                     String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "Idempotency-Key header is required");
        }
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("microcrystalSerial", body.microcrystalSerial());
        fields.put("connectionProof", body.connectionProof());
        fields.put("capabilities", body.capabilities());
        fields.put("observationEpoch", body.observationEpoch());
        fields.put("observationSeq", body.observationSeq());
        fields.put("observedAt", body.observedAt().toString());
        fields.put("state", body.state());
        String payloadHash = CanonicalObjectBuilder.forOperation(OP_OBSERVE)
                .fields(fields).payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OP_OBSERVE, idempotencyKey, payloadHash);
        return switch (outcome) {
            case BeginOutcome.ReplaySucceeded replay -> new ObservationOutcome(
                    projectReplay(replay), true);
            case BeginOutcome.ReplayRejected rejected ->
                    throw IdempotencyService.replayedRejection(rejected);
            case BeginOutcome.NewAttempt fresh -> new ObservationOutcome(
                    reportFresh(principal, body, fresh.handle()), false);
        };
    }

    private DeviceDtos.MicrocrystalObservationAck projectReplay(BeginOutcome.ReplaySucceeded replay) {
        if (!RESOURCE_TYPE.equals(replay.resourceType()) || replay.resourceId() == null) {
            throw new ApiException(ErrorCode.INTERNAL, "unexpected replay resource");
        }
        JsonNode summary = replay.resultSummary();
        return new DeviceDtos.MicrocrystalObservationAck(replay.resourceId().toString(),
                summary.path("accepted").asBoolean(false),
                summary.path("capabilityRevision").asText("0"),
                summary.path("receivedAt").asText(null));
    }

    private DeviceDtos.MicrocrystalObservationAck reportFresh(
            PrincipalContext principal, DeviceDtos.MicrocrystalObservationBody body,
            IdempotencyHandle handle) {
        ProofFailure failure = connectionProofVerifier.verify(
                body.connectionProof(), principal, body.microcrystalSerial()).failure();
        if (failure != null) {
            rejectAndThrow(handle, proofError(failure));
        }

        Integer schemaVersion = schemaVersionOf(body.capabilities());
        if (schemaVersion == null) {
            rejectAndThrow(handle, new ApiException(ErrorCode.INVALID_INPUT,
                    "capabilities.schemaVersion must be an integer >= 1"));
        }
        String requestedRevision = revisionOf(body.capabilities());
        if (requestedRevision == null) {
            rejectAndThrow(handle, new ApiException(ErrorCode.INVALID_INPUT,
                    "capabilities.revision must be an unsigned decimal bigint string"));
        }

        Observer observer = observerFor(principal);
        long seq = parseBigint(body.observationSeq());
        return txTemplate.execute(status -> {
            UUID microcrystalId = locateOrRegister(body.microcrystalSerial(), status);
            Row row = selectForUpdate(microcrystalId);
            if (row == null) {
                throw new ApiException(ErrorCode.INTERNAL,
                        "microcrystal row missing after locate");
            }
            Decision decision = decide(row, observer, principal.credentialVersion(),
                    principal.sessionId(), body.observationEpoch(), seq);
            if (!decision.accepted()) {
                String existingRevision = currentRevision(row.capabilities());
                Instant received = row.receivedAt() == null ? Instant.now() : row.receivedAt();
                DeviceDtos.MicrocrystalObservationAck ack =
                        new DeviceDtos.MicrocrystalObservationAck(microcrystalId.toString(), false,
                                existingRevision, EnvelopeSupport.rfc3339(received));
                idempotencyService.completeSuccess(handle, RESOURCE_TYPE, microcrystalId,
                        summary(microcrystalId, false, existingRevision, received));
                return ack;
            }

            Instant now = Instant.now();
            Map<String, Object> capabilities = buildCapabilities(body.capabilities(),
                    schemaVersion, requestedRevision);
            Map<String, Object> latest = new LinkedHashMap<>();
            latest.put("schema_version", 1);
            latest.put("observer_generation", decision.generation());
            latest.put("observer_sessions", ObservationSessions.toJson(decision.sessions()));
            latest.put("observer_credential_version", principal.credentialVersion());
            latest.put("state", body.state());
            int updated = jdbc.update("UPDATE microcrystals SET capabilities = ?::jsonb,"
                            + " latest_observation = ?::jsonb, observer_type = ?, observer_ref = ?,"
                            + " observation_epoch = ?, observation_seq = ?, observed_at = ?,"
                            + " received_at = ?, updated_at = now()"
                            + " WHERE id = ? AND observation_epoch IS NOT DISTINCT FROM ?"
                            + " AND observation_seq IS NOT DISTINCT FROM ?",
                    DeviceJson.write(capabilities), DeviceJson.write(latest), observer.type(),
                    observer.ref(), body.observationEpoch(), seq, Timestamp.from(body.observedAt()),
                    Timestamp.from(now), microcrystalId, row.observationEpoch(), row.observationSeq());
            if (updated == 0) {
                throw ApiException.requestInProgress(1);
            }
            idempotencyService.completeSuccess(handle, RESOURCE_TYPE, microcrystalId,
                    summary(microcrystalId, true, requestedRevision, now));
            return new DeviceDtos.MicrocrystalObservationAck(microcrystalId.toString(), true,
                    requestedRevision, EnvelopeSupport.rfc3339(now));
        });
    }

    private UUID locateOrRegister(String serial, TransactionStatus status) {
        List<UUID> existing = jdbc.query("SELECT id FROM microcrystals WHERE serial_no = ?",
                (rs, i) -> rs.getObject("id", UUID.class), serial);
        if (!existing.isEmpty()) {
            return existing.get(0);
        }
        UUID id = UUID.randomUUID();
        Object savepoint = status.createSavepoint();
        try {
            jdbc.update("INSERT INTO microcrystals (id, serial_no, created_at, updated_at)"
                    + " VALUES (?, ?, now(), now())", id, serial);
            status.releaseSavepoint(savepoint);
            return id;
        } catch (DuplicateKeyException race) {
            status.rollbackToSavepoint(savepoint);
            status.releaseSavepoint(savepoint);
            log.info("microcrystal serial insert raced uq_microcrystal_serial; re-reading");
            List<UUID> again = jdbc.query("SELECT id FROM microcrystals WHERE serial_no = ?",
                    (rs, i) -> rs.getObject("id", UUID.class), serial);
            if (again.isEmpty()) {
                throw new ApiException(ErrorCode.INTERNAL,
                        "microcrystal insert raced but row is not visible");
            }
            return again.get(0);
        }
    }

    private Row selectForUpdate(UUID microcrystalId) {
        List<Row> rows = jdbc.query("SELECT observer_type, observer_ref, observation_epoch,"
                        + " observation_seq, capabilities::text AS capabilities, received_at,"
                        + " latest_observation::text AS latest_observation"
                        + " FROM microcrystals WHERE id = ? FOR UPDATE",
                (rs, i) -> new Row(rs.getString("observer_type"), rs.getString("observer_ref"),
                        rs.getString("observation_epoch"),
                        rs.getObject("observation_seq") == null ? null
                                : rs.getLong("observation_seq"),
                        rs.getString("capabilities"),
                        rs.getTimestamp("received_at") == null ? null
                                : rs.getTimestamp("received_at").toInstant(),
                        rs.getString("latest_observation")),
                microcrystalId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /** accepted=false 时 generation/sessions 仅作诊断，绝不写库。 */
    private record Decision(boolean accepted, int generation,
                            List<ObservationSessions.Session> sessions) {
    }

    /**
     * 服务端会话代次判定（Oracle 第二轮 #2）。来源变化 → 重置并 generation=1；
     * 来源相同 → 按 {@link ObservationSessions} 的服务端次序：更大代次接受重置，
     * 同代次要求 epoch 一致且 seq 严格更大，旧代次一律拒绝。
     */
    private static Decision decide(Row row, Observer observer, long credentialVersion,
                                   String sessionId, String epoch, long seq) {
        Map<String, Object> observed = DeviceJson.parseObject(row.latestObservation());
        boolean sourceChanged = row.observerType() == null || row.observerRef() == null
                || !row.observerType().equals(observer.type())
                || !row.observerRef().equals(observer.ref());
        if (sourceChanged) {
            // 新来源 = 新来源会话：接受并重置，服务端记为 generation=1。
            return new Decision(true, 1, ObservationSessions.freshSessions(sessionId));
        }
        ObservationSessions.Resolution resolution = ObservationSessions.resolve(
                observed.get("observer_sessions"),
                DeviceJson.longAt(observed, "observer_credential_version"),
                DeviceJson.longAt(observed, "observer_generation"),
                credentialVersion, sessionId);
        boolean accepted = switch (resolution.relation()) {
            case FIRST_OR_ADVANCED, NEWER -> true;
            case SAME -> row.observationEpoch() != null && row.observationEpoch().equals(epoch)
                    && row.observationSeq() != null && seq > row.observationSeq();
            case STALE -> false;
        };
        return new Decision(accepted, resolution.generation(), resolution.sessions());
    }

    private static Map<String, Object> buildCapabilities(Map<String, Object> requested,
                                                         int schemaVersion, String revision) {
        Map<String, Object> capabilities = new LinkedHashMap<>();
        capabilities.put("schema_version", schemaVersion);
        capabilities.put("revision", revision);
        for (Map.Entry<String, Object> entry : requested.entrySet()) {
            if ("schemaVersion".equals(entry.getKey()) || "revision".equals(entry.getKey())) {
                continue;
            }
            capabilities.put(entry.getKey(), entry.getValue());
        }
        return capabilities;
    }

    private static Map<String, Object> summary(UUID microcrystalId, boolean accepted,
                                               String capabilityRevision, Instant receivedAt) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("microcrystalId", microcrystalId.toString());
        summary.put("accepted", accepted);
        summary.put("capabilityRevision", capabilityRevision);
        summary.put("receivedAt", EnvelopeSupport.rfc3339(receivedAt));
        return summary;
    }

    // ---------------- M2-A05 ----------------

    public DeviceDtos.CapabilitiesView capabilities(PrincipalContext principal, UUID microcrystalId,
                                                    String connectionProof) {
        ReadRow view = loadForRead(microcrystalId);
        if (view == null) {
            throw notVisible();
        }
        switch (resolveAccess(principal, view, connectionProof)) {
            case ALLOW -> {
                // continue
            }
            case DENY_REQUIRED -> throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "a valid connection proof is required to read this microcrystal");
            case DENY_NOT_VISIBLE -> throw notVisible();
        }
        Map<String, Object> capabilities = DeviceJson.parseObject(view.capabilities());
        String revision = currentRevision(view.capabilities());
        boolean stale = view.receivedAt() == null
                || Duration.between(view.receivedAt(), Instant.now()).getSeconds()
                > props.stalenessSecondsOrDefault();
        return new DeviceDtos.CapabilitiesView(capabilities, revision,
                view.observedAt() == null ? null : EnvelopeSupport.rfc3339(view.observedAt()),
                view.receivedAt() == null ? null : EnvelopeSupport.rfc3339(view.receivedAt()),
                stale);
    }

    private record ReadRow(String serialNo, String observerType, String observerRef,
                           String capabilities, Instant observedAt, Instant receivedAt) {
    }

    private ReadRow loadForRead(UUID microcrystalId) {
        List<ReadRow> rows = jdbc.query("SELECT serial_no, observer_type, observer_ref,"
                        + " capabilities::text AS capabilities, observed_at, received_at"
                        + " FROM microcrystals WHERE id = ?",
                (rs, i) -> new ReadRow(rs.getString("serial_no"), rs.getString("observer_type"),
                        rs.getString("observer_ref"), rs.getString("capabilities"),
                        rs.getTimestamp("observed_at") == null ? null
                                : rs.getTimestamp("observed_at").toInstant(),
                        rs.getTimestamp("received_at") == null ? null
                                : rs.getTimestamp("received_at").toInstant()),
                microcrystalId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private enum Access {
        ALLOW, DENY_REQUIRED, DENY_NOT_VISIBLE
    }

    private Access resolveAccess(PrincipalContext principal, ReadRow row, String connectionProof) {
        Observer observer = observerFor(principal);
        if (connectionProof != null && !connectionProof.isBlank()) {
            ProofFailure failure = connectionProofVerifier.verify(connectionProof, principal,
                    row.serialNo()).failure();
            if (failure == null) {
                return Access.ALLOW;
            }
            // 证明有效格式但绑定的是另一个微晶 → 按不可见处理；其余非法证明 → 403。
            return failure == ProofFailure.WRONG_MICROCRYSTAL
                    ? Access.DENY_NOT_VISIBLE : Access.DENY_REQUIRED;
        }
        boolean observerMatches = row.observerRef() != null
                && observer.type().equals(row.observerType())
                && observer.ref().equals(row.observerRef());
        if (observerMatches) {
            return Access.ALLOW;
        }
        // 从未被观察 → 无上下文可推定（403）；已被他人观察 → 不可见（404）。
        return row.observerRef() == null ? Access.DENY_REQUIRED : Access.DENY_NOT_VISIBLE;
    }

    // ---------------- shared ----------------

    private void rejectAndThrow(IdempotencyHandle handle, ApiException error) {
        txTemplate.execute(status -> {
            idempotencyService.completeRejected(handle, error.getCode(), error.getHttpStatus(),
                    error.getMessage(), error.isRetryable(), error.getDetails());
            return null;
        });
        throw error;
    }

    private static ApiException proofError(ProofFailure failure) {
        return switch (failure) {
            case MISSING, MALFORMED -> new ApiException(ErrorCode.INVALID_INPUT,
                    "connectionProof is missing or malformed");
            case UNSUPPORTED_VERSION -> new ApiException(ErrorCode.UNSUPPORTED_CONTRACT,
                    "connectionProof contract version is not supported");
            default -> new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "connectionProof could not be verified for this control side");
        };
    }

    private static Observer observerFor(PrincipalContext principal) {
        return principal.principalType() == PrincipalType.APP
                ? new Observer("app_account", principal.accountUuid() + ":" + principal.installationId())
                : new Observer("gimbal", principal.gimbalUuid().toString());
    }

    private static Integer schemaVersionOf(Map<String, Object> capabilities) {
        Object value = capabilities == null ? null : capabilities.get("schemaVersion");
        if (value instanceof Number number) {
            double d = number.doubleValue();
            if (d >= 1 && d == Math.rint(d) && d <= Integer.MAX_VALUE) {
                return (int) d;
            }
        }
        return null;
    }

    private static String revisionOf(Map<String, Object> capabilities) {
        Object value = capabilities == null ? null : capabilities.get("revision");
        if (value instanceof String text && text.matches(BIGINT)) {
            return text;
        }
        return null;
    }

    private static String currentRevision(String capabilitiesRaw) {
        String revision = revisionOf(DeviceJson.parseObject(capabilitiesRaw));
        return revision == null ? "0" : revision;
    }

    private static long parseBigint(String value) {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException e) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "observationSeq out of bigint range");
        }
    }

    private static ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, NOT_VISIBLE_MESSAGE);
    }
}

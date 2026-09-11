package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.CareExecutionAdmission;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.CareExecutionRevalidation;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.CaptureDto;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.M4A03Metadata;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.M4A04Metadata;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.VerificationDto;
import cn.yuanxin.mvp.web.care.CareExecutionRepository.CareExecutionRow;
import cn.yuanxin.mvp.web.care.CareExecutionRepository.NewExecution;
import cn.yuanxin.mvp.web.care.CarePlanRepository.CarePlanRow;
import cn.yuanxin.mvp.web.care.GimbalReadRepository.GimbalPointer;
import cn.yuanxin.mvp.web.care.MicrocrystalRepository.MicrocrystalRow;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.BeginOutcome;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import cn.yuanxin.mvp.web.idempotency.IdempotencyHandle;
import cn.yuanxin.mvp.web.idempotency.IdempotencyService;
import cn.yuanxin.mvp.web.idempotency.StaleAttemptException;
import cn.yuanxin.mvp.web.media.MediaIntakeService;
import cn.yuanxin.mvp.web.media.MediaPurpose;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.NestedExceptionUtils;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * M4-A03（登记新执行）/ M4-A04（连续性失效后重新核验）编排。
 *
 * <p>事务边界：T13 {@code begin}、外部人脸与存储、锁外读取/验权全部在事务外；
 * 最终写入用 {@link TransactionTemplate} 单短事务，按下述锁序持锁复核后再写：
 * A03 = T03(云台) → T04 → T06 → INSERT T07 → T02(APP)；A04 = T03(云台) → T04
 * → T06 → T07 → T02(APP)。任何锁内复核失败都让事务回滚，再在独立短事务里
 * 把同一 Idempotency-Key 记为 rejected（确定性拒绝；同键重试重放原拒绝）。</p>
 *
 * <p><b>人脸准入协议缺口（必须保留此说明）：</b>真实 1:1「当前人脸 vs 方案成员」
 * 比对需要可信成员参考照，而 {@link FaceProvider#classify(String, byte[])} 端口
 * 没有成员参数。MVP 以 {@code MATCHED} 表示“与方案成员一致”，由测试替身/
 * 未来真实提供方保证该语义；接入缺口不改变本端点的写入语义。</p>
 */
@Service
public class CareAdmissionService {

    private static final Logger log = LoggerFactory.getLogger(CareAdmissionService.class);

    public static final String OPERATION_CREATE = "care.execution.create";
    public static final String OPERATION_REVALIDATE = "care.execution.revalidate";
    public static final String RESOURCE_TYPE = "care_execution";

    private static final String DEVICE_OCCUPIED_MESSAGE =
            "device is occupied by another open execution";
    private static final String EMPTY_OBJECT = "{}";

    private final CareAuthorization authorization;
    private final CareProjections projections;
    private final CarePlanProjection planProjection;
    private final CarePlanRepository planRepository;
    private final CareExecutionRepository executionRepository;
    private final GimbalReadRepository gimbalRepository;
    private final MicrocrystalRepository microcrystalRepository;
    private final CareAccessRepository accessRepository;
    private final MediaIntakeService mediaIntakeService;
    private final FaceProvider faceProvider;
    private final IdempotencyService idempotencyService;
    private final TransactionTemplate txTemplate;
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public CareAdmissionService(CareAuthorization authorization, CareProjections projections,
                                CarePlanProjection planProjection,
                                CarePlanRepository planRepository,
                                CareExecutionRepository executionRepository,
                                GimbalReadRepository gimbalRepository,
                                MicrocrystalRepository microcrystalRepository,
                                CareAccessRepository accessRepository,
                                MediaIntakeService mediaIntakeService, FaceProvider faceProvider,
                                IdempotencyService idempotencyService,
                                TransactionTemplate txTemplate, JdbcTemplate jdbc,
                                ObjectMapper objectMapper) {
        this.authorization = authorization;
        this.projections = projections;
        this.planProjection = planProjection;
        this.planRepository = planRepository;
        this.executionRepository = executionRepository;
        this.gimbalRepository = gimbalRepository;
        this.microcrystalRepository = microcrystalRepository;
        this.accessRepository = accessRepository;
        this.mediaIntakeService = mediaIntakeService;
        this.faceProvider = faceProvider;
        this.idempotencyService = idempotencyService;
        this.txTemplate = txTemplate;
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    /** 成功结果 + 是否来自 T13 重放（控制器据此决定 201/200）。 */
    public record AdmissionOutcome(CareExecutionAdmission data, boolean replayed) {
    }

    public record RevalidationOutcome(CareExecutionRevalidation data, boolean replayed) {
    }

    // ======================= M4-A03 =======================

    public AdmissionOutcome admit(PrincipalContext principal, M4A03Metadata meta, byte[] face,
                                  String idempotencyKey) {
        boolean app = principal.principalType() == PrincipalType.APP;
        if (app) {
            if (meta.planId() == null || meta.currentTaskId() != null
                    || meta.currentAssessmentRevision() != null) {
                throw invalid("app caller must provide only planId");
            }
        } else if (meta.currentTaskId() == null || meta.currentAssessmentRevision() == null
                || meta.planId() != null) {
            throw invalid("gimbal caller must provide only currentTaskId and currentAssessmentRevision");
        }
        if (!"admission".equals(meta.capture().purpose())) {
            throw invalid("capture.purpose must be admission");
        }
        parseInstant(meta.capture().capturedAt(), "capture.capturedAt");
        Long providedRevision = meta.currentAssessmentRevision() == null ? null
                : CareBigints.parse(meta.currentAssessmentRevision(), "currentAssessmentRevision");

        String payloadHash = CanonicalObjectBuilder.forOperation(OPERATION_CREATE)
                .pathParams(Map.of())
                .fields(createCanonicalFields(meta))
                .imageParts(MediaIntakeService.partDigests(Map.of("face", face)))
                .payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OPERATION_CREATE, idempotencyKey, payloadHash);
        if (outcome instanceof BeginOutcome.ReplaySucceeded replay) {
            return new AdmissionOutcome(projectAdmissionReplay(replay, principal), true);
        }
        if (outcome instanceof BeginOutcome.ReplayRejected rejected) {
            throw IdempotencyService.replayedRejection(rejected);
        }
        IdempotencyHandle handle = ((BeginOutcome.NewAttempt) outcome).handle();

        try {
            return runAdmission(handle, principal, meta, face, providedRevision);
        } catch (ApiException ex) {
            if (deterministic(ex.getCode())) {
                bestEffortReject(handle, ex.getCode(), ex.getMessage(), ex.getDetails());
            }
            throw ex;
        } catch (DuplicateKeyException dup) {
            if (isDeviceOccupiedConstraint(dup)) {
                bestEffortReject(handle, ErrorCode.DEVICE_OCCUPIED, DEVICE_OCCUPIED_MESSAGE, null);
                throw new ApiException(ErrorCode.DEVICE_OCCUPIED, DEVICE_OCCUPIED_MESSAGE);
            }
            throw new ApiException(ErrorCode.INTERNAL, "care execution registration failed");
        }
    }

    private Map<String, Object> createCanonicalFields(M4A03Metadata meta) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("microcrystalId", meta.microcrystalId().toString());
        fields.put("connectionProof", meta.connectionProof());
        fields.put("capture", captureCanonical(meta.capture()));
        fields.put("consentEvidenceRef", meta.consentEvidenceRef());
        fields.put("planId", meta.planId() == null ? null : meta.planId().toString());
        fields.put("currentTaskId", meta.currentTaskId() == null ? null : meta.currentTaskId().toString());
        fields.put("currentAssessmentRevision", meta.currentAssessmentRevision());
        return fields;
    }

    private AdmissionOutcome runAdmission(IdempotencyHandle handle, PrincipalContext principal,
                                          M4A03Metadata meta, byte[] face, Long providedRevision) {
        boolean app = principal.principalType() == PrincipalType.APP;

        // 步骤 3：锁外方案解析
        CarePlanRow plan;
        if (app) {
            plan = planRepository.findById(meta.planId()).orElseThrow(() -> authorization.notVisible());
        } else {
            GimbalPointer pointer = gimbalRepository.findPointer(principal.gimbalUuid())
                    .orElseThrow(this::taskReplaced);
            if (pointer.currentAssessmentId() == null
                    || !pointer.currentAssessmentId().equals(meta.currentTaskId())
                    || pointer.currentAssessmentRevision() != providedRevision) {
                throw taskReplaced();
            }
            plan = planRepository.findByAssessmentId(meta.currentTaskId())
                    .orElseThrow(() -> authorization.notVisible());
        }

        // 步骤 4：锁外预检
        if (app && !authorization.hasActiveGrant(principal, plan.memberId())) {
            throw authorization.notVisible();
        }
        if (!"ready".equals(plan.generationStatus())) {
            throw planNotReady(null);
        }
        if (plan.targetCount() != null && plan.completedCount() >= plan.targetCount()) {
            throw planCompleted();
        }
        MicrocrystalRow microcrystal = microcrystalRepository.findById(meta.microcrystalId())
                .orElseThrow(() -> authorization.notVisible());
        requireCapabilityCovered(plan, microcrystal);

        // 步骤 5：媒体受理（锁外）
        var ingested = mediaIntakeService.ingest(principal, MediaPurpose.EXECUTION_FACE,
                handle.requestId(), Map.of("face", face));
        UUID mediaId = ingested.get("face").media().id();

        // 步骤 6：人脸核验（锁外）
        requireFaceMatched(faceProvider.classify("admission", face));

        // 步骤 7：最终短事务
        AdmissionTx tx = txTemplate.execute(status -> runAdmissionTx(handle, principal, meta, plan,
                microcrystal.id(), mediaId, providedRevision));
        if (tx == null) {
            throw new ApiException(ErrorCode.INTERNAL, "admission transaction produced no result");
        }
        CareExecutionAdmission data = new CareExecutionAdmission(
                tx.executionId().toString(),
                "admitted",
                controllerRef(principal),
                tx.plan().memberId().toString(),
                tx.plan().id().toString(),
                planProjection.execution(tx.plan().planPayload()),
                projections.progressFor(tx.plan()),
                new VerificationDto("1", meta.capture().captureId(),
                        meta.capture().clientContinuityId(), rfc3339(tx.now()), null,
                        "admission", false),
                tx.executionId().toString());
        return new AdmissionOutcome(data, false);
    }

    private record AdmissionTx(UUID executionId, CarePlanRow plan, Instant now) {
    }

    private AdmissionTx runAdmissionTx(IdempotencyHandle handle, PrincipalContext principal,
                                       M4A03Metadata meta, CarePlanRow plan, UUID microcrystalId,
                                       UUID mediaId, Long providedRevision) {
        boolean app = principal.principalType() == PrincipalType.APP;
        // a. T03（仅云台）
        if (!app) {
            GimbalPointer pointer = gimbalRepository.lockById(principal.gimbalUuid())
                    .orElseThrow(this::taskReplaced);
            if (pointer.currentAssessmentId() == null
                    || !pointer.currentAssessmentId().equals(meta.currentTaskId())
                    || pointer.currentAssessmentRevision() != providedRevision) {
                throw taskReplaced();
            }
        }
        // b. T04
        MicrocrystalRow microcrystal = microcrystalRepository.lockById(microcrystalId)
                .orElseThrow(() -> authorization.notVisible());
        // c. T06 重检 ready/K<N/能力
        CarePlanRow locked = planRepository.lockById(plan.id())
                .orElseThrow(() -> authorization.notVisible());
        if (!"ready".equals(locked.generationStatus())) {
            throw planNotReady(null);
        }
        if (locked.targetCount() != null && locked.completedCount() >= locked.targetCount()) {
            throw planCompleted();
        }
        requireCapabilityCovered(locked, microcrystal);

        // d. INSERT T07
        UUID executionId = UUID.randomUUID();
        Instant now = Instant.now();
        String controllerType = app ? "app" : "gimbal";
        NewExecution row = new NewExecution(
                executionId, locked.id(), locked.memberId(), microcrystalId,
                controllerType,
                app ? principal.accountUuid() : null,
                app ? principal.installationId() : null,
                app ? null : principal.gimbalUuid(),
                locked.assessmentId(),
                writeJson(buildPlanSnapshot(locked, mediaId, meta, now)),
                writeJson(buildLatestVerification(mediaId, meta.capture(), "admission", now)),
                now,
                executionId.toString(),
                handle.requestId());
        executionRepository.insert(row);

        // T02（仅 APP；与撤销交错以锁内结果为准）
        if (app && !accessRepository.hasActiveGrantForUpdate(principal.accountUuid(),
                locked.memberId())) {
            throw authorization.notVisible();
        }

        // e. 图片补归属 + f. T13 succeeded
        updateMediaOwnership(mediaId, executionId, locked.memberId());
        idempotencyService.completeSuccess(handle, RESOURCE_TYPE, executionId, Map.of(
                "execution_id", executionId.toString(),
                "plan_id", locked.id().toString(),
                "member_id", locked.memberId().toString(),
                "controller_type", controllerType,
                "verification_revision", "1",
                "record_stream_epoch", executionId.toString(),
                "admitted_at", rfc3339(now)));
        return new AdmissionTx(executionId, locked, now);
    }

    private CareExecutionAdmission projectAdmissionReplay(BeginOutcome.ReplaySucceeded replay,
                                                          PrincipalContext principal) {
        if (!RESOURCE_TYPE.equals(replay.resourceType()) || replay.resourceId() == null) {
            throw new ApiException(ErrorCode.INTERNAL, "unexpected replay resource");
        }
        CareExecutionRow row = executionRepository.findById(replay.resourceId())
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, row)) {
            throw authorization.notVisible();
        }
        CarePlanRow plan = planRepository.findById(row.planId())
                .orElseThrow(() -> new ApiException(ErrorCode.INTERNAL,
                        "care execution references a missing plan"));
        if (!authorization.hasPlanReadEligibility(principal, plan)) {
            // 重放不把“原控制端”当持续读取权限：T13 仍 succeeded，仅本响应 404
            throw authorization.notVisible();
        }
        return new CareExecutionAdmission(
                row.id().toString(),
                "admitted",
                projections.controllerRef(row),
                row.memberId().toString(),
                row.planId().toString(),
                snapshotExecutionParams(row.planSnapshot()),
                projections.progressFor(plan),
                verificationProjection(row.latestVerification(),
                        CareBigints.out(row.verificationRevision()), row.lastVerifiedAt(),
                        "admission", true),
                row.observationEpoch());
    }

    // ======================= M4-A04 =======================

    public RevalidationOutcome revalidate(PrincipalContext principal, UUID executionId,
                                          M4A04Metadata meta, byte[] face, String idempotencyKey) {
        if (!"revalidation".equals(meta.capture().purpose())) {
            throw invalid("capture.purpose must be revalidation");
        }
        JsonNode reportedMicrocrystalState = meta.reportedMicrocrystalState();
        if (reportedMicrocrystalState != null && !reportedMicrocrystalState.isNull()
                && !reportedMicrocrystalState.isObject()) {
            throw invalid("reportedMicrocrystalState must be a JSON object");
        }
        parseInstant(meta.capture().capturedAt(), "capture.capturedAt");
        long expectedRevision = CareBigints.parse(meta.expectedVerificationRevision(),
                "expectedVerificationRevision");

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("expectedVerificationRevision", meta.expectedVerificationRevision());
        fields.put("capture", captureCanonical(meta.capture()));
        fields.put("consentEvidenceRef", meta.consentEvidenceRef());
        fields.put("reportedMicrocrystalState", jsonOrNull(meta.reportedMicrocrystalState()));
        String payloadHash = CanonicalObjectBuilder.forOperation(OPERATION_REVALIDATE)
                .pathParams(Map.of("executionId", executionId.toString()))
                .fields(fields)
                .imageParts(MediaIntakeService.partDigests(Map.of("face", face)))
                .payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OPERATION_REVALIDATE, idempotencyKey, payloadHash);
        if (outcome instanceof BeginOutcome.ReplaySucceeded replay) {
            return new RevalidationOutcome(projectRevalidationReplay(replay, principal), true);
        }
        if (outcome instanceof BeginOutcome.ReplayRejected rejected) {
            throw IdempotencyService.replayedRejection(rejected);
        }
        IdempotencyHandle handle = ((BeginOutcome.NewAttempt) outcome).handle();

        try {
            return runRevalidation(handle, principal, executionId, meta, face, expectedRevision);
        } catch (ApiException ex) {
            if (deterministic(ex.getCode())) {
                bestEffortReject(handle, ex.getCode(), ex.getMessage(), ex.getDetails());
            }
            throw ex;
        } catch (DuplicateKeyException dup) {
            throw new ApiException(ErrorCode.INTERNAL, "care revalidation update failed");
        }
    }

    private RevalidationOutcome runRevalidation(IdempotencyHandle handle, PrincipalContext principal,
                                                UUID executionId, M4A04Metadata meta, byte[] face,
                                                long expectedRevision) {
        // 步骤 1：锁外
        CareExecutionRow row = executionRepository.findById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, row)) {
            throw authorization.notVisible();
        }
        if (!"paused".equals(row.status())) {
            throw executionNotResumable(notResumableReason(row.status()));
        }
        CarePlanRow plan = planRepository.findById(row.planId())
                .orElseThrow(() -> new ApiException(ErrorCode.INTERNAL,
                        "care execution references a missing plan"));
        if (plan.targetCount() != null && plan.completedCount() >= plan.targetCount()) {
            throw executionNotResumable("plan_completed");
        }
        if (row.verificationRevision() != expectedRevision) {
            throw executionNotResumable("verification_revision_mismatch");
        }
        if (principal.principalType() == PrincipalType.GIMBAL) {
            GimbalPointer pointer = gimbalRepository.findPointer(principal.gimbalUuid())
                    .orElseThrow(this::taskReplaced);
            if (pointer.currentAssessmentId() == null
                    || !pointer.currentAssessmentId().equals(plan.assessmentId())) {
                throw taskReplaced();
            }
        } else if (!authorization.hasActiveGrant(principal, row.memberId())) {
            throw authorization.notVisible();
        }

        // 步骤 2：媒体与人脸（锁外）
        var ingested = mediaIntakeService.ingest(principal, MediaPurpose.REVALIDATION_FACE,
                handle.requestId(), Map.of("face", face));
        UUID mediaId = ingested.get("face").media().id();
        requireFaceMatched(faceProvider.classify("revalidation", face));

        // 步骤 3：最终短事务
        RevalidationTx tx = txTemplate.execute(status -> runRevalidationTx(handle, principal,
                executionId, meta, plan, mediaId, expectedRevision));
        if (tx == null) {
            throw new ApiException(ErrorCode.INTERNAL, "revalidation transaction produced no result");
        }
        CareExecutionRevalidation data = new CareExecutionRevalidation(
                tx.executionId().toString(),
                "paused",
                tx.plan().id().toString(),
                snapshotExecutionParams(tx.planSnapshot()),
                projections.progressFor(tx.plan()),
                new VerificationDto(CareBigints.out(tx.newRevision()), meta.capture().captureId(),
                        meta.capture().clientContinuityId(), rfc3339(tx.now()), null,
                        "revalidation", false));
        return new RevalidationOutcome(data, false);
    }

    private record RevalidationTx(UUID executionId, CarePlanRow plan, String planSnapshot,
                                  long newRevision, Instant now) {
    }

    private RevalidationTx runRevalidationTx(IdempotencyHandle handle, PrincipalContext principal,
                                             UUID executionId, M4A04Metadata meta, CarePlanRow plan,
                                             UUID mediaId, long expectedRevision) {
        boolean app = principal.principalType() == PrincipalType.APP;
        if (!app) {
            GimbalPointer pointer = gimbalRepository.lockById(principal.gimbalUuid())
                    .orElseThrow(this::taskReplaced);
            if (pointer.currentAssessmentId() == null
                    || !pointer.currentAssessmentId().equals(plan.assessmentId())) {
                throw taskReplaced();
            }
        }
        CareExecutionRow lockedRef = executionRepository.findById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        microcrystalRepository.lockById(lockedRef.microcrystalId())
                .orElseThrow(() -> authorization.notVisible());
        CarePlanRow lockedPlan = planRepository.lockById(plan.id())
                .orElseThrow(() -> authorization.notVisible());
        if (lockedPlan.targetCount() != null && lockedPlan.completedCount() >= lockedPlan.targetCount()) {
            throw executionNotResumable("plan_completed");
        }
        CareExecutionRow locked = executionRepository.lockById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, locked)) {
            throw authorization.notVisible();
        }
        if (!"paused".equals(locked.status())) {
            throw executionNotResumable(notResumableReason(locked.status()));
        }
        if (locked.verificationRevision() != expectedRevision) {
            throw executionNotResumable("verification_revision_mismatch");
        }
        if (app && !accessRepository.hasActiveGrantForUpdate(principal.accountUuid(),
                locked.memberId())) {
            throw authorization.notVisible();
        }

        long newRevision = locked.verificationRevision() + 1;
        Instant now = Instant.now();
        String latestVerification = writeJson(
                buildLatestVerification(mediaId, meta.capture(), "revalidation", now));
        jdbc.update("UPDATE care_executions SET verification_revision = verification_revision + 1,"
                        + " last_verified_at = ?, latest_verification = CAST(? AS jsonb),"
                        + " latest_observation = CASE WHEN latest_observation IS NULL THEN NULL"
                        + "   ELSE jsonb_set(latest_observation, '{continuity_invalidated}',"
                        + "        'false'::jsonb, true) END,"
                        + " updated_at = now() WHERE id = ?",
                Timestamp.from(now), latestVerification, executionId);
        updateMediaOwnership(mediaId, executionId, locked.memberId());
        idempotencyService.completeSuccess(handle, RESOURCE_TYPE, executionId, Map.of(
                "execution_id", executionId.toString(),
                "verification_revision", Long.toString(newRevision),
                "revalidated_at", rfc3339(now)));
        return new RevalidationTx(executionId, lockedPlan, locked.planSnapshot(), newRevision, now);
    }

    private CareExecutionRevalidation projectRevalidationReplay(BeginOutcome.ReplaySucceeded replay,
                                                                PrincipalContext principal) {
        if (!RESOURCE_TYPE.equals(replay.resourceType()) || replay.resourceId() == null) {
            throw new ApiException(ErrorCode.INTERNAL, "unexpected replay resource");
        }
        CareExecutionRow row = executionRepository.findById(replay.resourceId())
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, row)) {
            throw authorization.notVisible();
        }
        CarePlanRow plan = planRepository.findById(row.planId())
                .orElseThrow(() -> new ApiException(ErrorCode.INTERNAL,
                        "care execution references a missing plan"));
        if (!authorization.hasPlanReadEligibility(principal, plan)) {
            throw authorization.notVisible();
        }
        return new CareExecutionRevalidation(
                row.id().toString(),
                row.status(),
                row.planId().toString(),
                snapshotExecutionParams(row.planSnapshot()),
                projections.progressFor(plan),
                verificationProjection(row.latestVerification(),
                        CareBigints.out(row.verificationRevision()), row.lastVerifiedAt(),
                        "revalidation", true));
    }

    // ======================= helpers =======================

    private static Map<String, Object> captureCanonical(CaptureDto capture) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("captureId", capture.captureId());
        map.put("capturedAt", capture.capturedAt());
        map.put("clientContinuityId", capture.clientContinuityId());
        map.put("purpose", capture.purpose());
        map.put("captureProofRef", capture.captureProofRef());
        return map;
    }

    /**
     * 能力覆盖最小规则（能力协议未冻结，MVP 裁量）：capabilities 为空对象 →
     * 未覆盖；若方案 input_snapshot 显式携带 {@code required_capability_revision}
     * 键，则 capabilities.revision 必须与其字符串化后相等。未来能力协议冻结后
     * 应替换为正式的批准参数/基线匹配。
     */
    private void requireCapabilityCovered(CarePlanRow plan, MicrocrystalRow microcrystal) {
        JsonNode caps = readJsonObject(microcrystal.capabilities());
        if (caps == null) {
            throw planNotReady("capability_not_covered");
        }
        JsonNode snapshot = readJsonObject(plan.inputSnapshot());
        if (snapshot != null && snapshot.hasNonNull("required_capability_revision")) {
            JsonNode required = snapshot.get("required_capability_revision");
            JsonNode actual = caps.get("revision");
            if (actual == null || actual.isNull()
                    || !required.asText().equals(actual.asText())) {
                throw planNotReady("capability_not_covered");
            }
        }
    }

    private void requireFaceMatched(FaceClassification classification) {
        switch (classification) {
            case MATCHED -> {
            }
            case RELIABLE_NEW, UNCERTAIN -> throw new ApiException(ErrorCode.FACE_NOT_VERIFIED,
                    "face does not match the plan member");
            case QUALITY_REJECTED -> throw new ApiException(ErrorCode.FACE_QUALITY_REJECTED,
                    "face image quality rejected");
            case DEPENDENCY_FAILED -> throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "face provider unavailable");
        }
    }

    private CareProjections.ControllerRef controllerRef(PrincipalContext principal) {
        if (principal.principalType() == PrincipalType.APP) {
            return new CareProjections.ControllerRef("app_account", principal.installationId(), null);
        }
        return new CareProjections.ControllerRef("gimbal", null, principal.gimbalUuid().toString());
    }

    private void updateMediaOwnership(UUID mediaId, UUID executionId, UUID memberId) {
        jdbc.update("UPDATE media_objects SET execution_id = ?, member_id = ?, updated_at = now()"
                + " WHERE id = ?", executionId, memberId, mediaId);
    }

    private JsonNode buildPlanSnapshot(CarePlanRow plan, UUID mediaId, M4A03Metadata meta,
                                       Instant now) {
        ObjectNode snapshot = objectMapper.createObjectNode();
        snapshot.put("schema_version", 1);
        snapshot.put("plan_id", plan.id().toString());
        snapshot.put("target_count", CareBigints.out(plan.targetCount()));
        Object summary = planProjection.summary(plan.planSummary());
        snapshot.set("summary", summary == null ? NullNode.getInstance() : (JsonNode) summary);
        Object params = planProjection.execution(plan.planPayload());
        snapshot.set("execution_params", params == null ? NullNode.getInstance() : (JsonNode) params);
        ObjectNode verification = snapshot.putObject("verification");
        verification.put("media_id", mediaId.toString());
        verification.put("capture_id", meta.capture().captureId());
        verification.put("client_continuity_id", meta.capture().clientContinuityId());
        verification.put("purpose", "admission");
        verification.put("verified_at", rfc3339(now));
        verification.put("classification", "MATCHED");
        return snapshot;
    }

    private JsonNode buildLatestVerification(UUID mediaId, CaptureDto capture, String purpose,
                                             Instant now) {
        ObjectNode verification = objectMapper.createObjectNode();
        verification.put("schema_version", 1);
        verification.put("capture_id", capture.captureId());
        verification.put("client_continuity_id", capture.clientContinuityId());
        verification.put("verified_at", rfc3339(now));
        verification.putNull("valid_until");
        verification.put("applicable_purpose", purpose);
        verification.put("media_id", mediaId.toString());
        verification.put("classification", "MATCHED");
        verification.put("continuity_invalidated", false);
        return verification;
    }

    private VerificationDto verificationProjection(String latestVerificationJson, String revision,
                                                   Instant fallbackVerifiedAt,
                                                   String fallbackPurpose, boolean replayed) {
        JsonNode node = readJsonObject(latestVerificationJson);
        String captureId = null;
        String continuityId = null;
        String purpose = null;
        Instant verifiedAt = null;
        if (node != null) {
            captureId = textOrNull(node, "capture_id", "captureId");
            continuityId = textOrNull(node, "client_continuity_id", "clientContinuityId");
            purpose = textOrNull(node, "applicable_purpose", "applicablePurpose");
            String rawVerifiedAt = textOrNull(node, "verified_at", "verifiedAt");
            if (rawVerifiedAt != null) {
                try {
                    verifiedAt = Instant.parse(rawVerifiedAt);
                } catch (DateTimeParseException ignored) {
                    verifiedAt = null;
                }
            }
        }
        if (verifiedAt == null) {
            verifiedAt = fallbackVerifiedAt;
        }
        if (purpose == null) {
            purpose = fallbackPurpose;
        }
        return new VerificationDto(revision, captureId, continuityId, rfc3339(verifiedAt), null,
                purpose, replayed);
    }

    private Object snapshotExecutionParams(String planSnapshotJson) {
        JsonNode snapshot = readJsonObject(planSnapshotJson);
        if (snapshot == null) {
            return null;
        }
        JsonNode params = snapshot.get("execution_params");
        return params == null || params.isNull() ? null : params;
    }

    private void bestEffortReject(IdempotencyHandle handle, ErrorCode code, String message,
                                  Map<String, Object> details) {
        if (handle == null) {
            return;
        }
        try {
            txTemplate.execute(status -> {
                idempotencyService.completeRejected(handle, code, code.defaultStatus().value(),
                        message == null ? code.name() : message, code.defaultRetryable(), details);
                return null;
            });
        } catch (StaleAttemptException ignored) {
            // 已被接管/已完成：保留既有结果，不阻断原始错误
        } catch (RuntimeException failure) {
            log.warn("best-effort idempotency rejection failed: {}", failure.getMessage());
        }
    }

    /** 确定性业务拒绝可写 T13 rejected；瞬时依赖失败保持 processing 供同键重试。 */
    private static boolean deterministic(ErrorCode code) {
        return switch (code) {
            case DEPENDENCY_UNAVAILABLE, DEPENDENCY_TIMEOUT, REQUEST_IN_PROGRESS, RATE_LIMITED,
                 INTERNAL, NOT_IMPLEMENTED, UNSUPPORTED_CONTRACT -> false;
            default -> true;
        };
    }

    private static boolean isDeviceOccupiedConstraint(DuplicateKeyException dup) {
        Throwable cause = NestedExceptionUtils.getMostSpecificCause(dup);
        String message = cause == null ? null : cause.getMessage();
        return message != null && (message.contains("uq_execution_open_microcrystal")
                || message.contains("uq_execution_open_gimbal"));
    }

    private static String notResumableReason(String status) {
        return switch (status) {
            case "admitted" -> "admitted_not_paused";
            case "unknown" -> "unknown_needs_fresh_paused_observation";
            case "stopped" -> "stopped_not_resumable";
            case "closed" -> "closed_not_resumable";
            case "running" -> "running_not_paused";
            default -> "not_paused";
        };
    }

    private JsonNode readJsonObject(String raw) {
        if (raw == null || raw.isBlank() || EMPTY_OBJECT.equals(raw.trim())) {
            return null;
        }
        try {
            JsonNode node = objectMapper.readTree(raw);
            return node != null && node.isObject() && node.size() > 0 ? node : null;
        } catch (Exception parseFailure) {
            return null;
        }
    }

    private static JsonNode jsonOrNull(JsonNode node) {
        return node == null || node.isNull() ? null : node;
    }

    private static String textOrNull(JsonNode node, String... keys) {
        for (String key : keys) {
            JsonNode value = node.get(key);
            if (value != null && value.isTextual() && !value.asText().isBlank()) {
                return value.asText();
            }
        }
        return null;
    }

    private String writeJson(JsonNode node) {
        try {
            return objectMapper.writeValueAsString(node);
        } catch (JsonProcessingException serializationFailure) {
            throw new ApiException(ErrorCode.INTERNAL, "execution projection serialization failed");
        }
    }

    private static Instant parseInstant(String raw, String field) {
        try {
            return Instant.parse(raw);
        } catch (DateTimeParseException invalid) {
            throw new ApiException(ErrorCode.INVALID_INPUT, field + " must be an RFC3339 date-time");
        }
    }

    private static String rfc3339(Instant instant) {
        return instant == null ? null : EnvelopeSupport.rfc3339(instant);
    }

    private static ApiException invalid(String message) {
        return new ApiException(ErrorCode.INVALID_INPUT, message);
    }

    private ApiException taskReplaced() {
        return new ApiException(ErrorCode.TASK_REPLACED, "gimbal current assessment was replaced");
    }

    private static ApiException planNotReady(String reason) {
        return reason == null
                ? new ApiException(ErrorCode.PLAN_NOT_READY, "care plan is not ready")
                : new ApiException(ErrorCode.PLAN_NOT_READY, "care plan is not ready",
                        Map.of("reason", reason));
    }

    private static ApiException planCompleted() {
        return new ApiException(ErrorCode.PLAN_COMPLETED, "care plan target count already reached");
    }

    private static ApiException executionNotResumable(String reason) {
        return new ApiException(ErrorCode.EXECUTION_NOT_RESUMABLE, "care execution is not resumable",
                Map.of("reason", reason));
    }
}

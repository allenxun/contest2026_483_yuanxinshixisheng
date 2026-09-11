package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.care.CareExecutionRepository.CareExecutionRow;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.AcknowledgedRecordDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.ClosureRequestDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.ClosureResultDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.ExecutionObservationDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.ExecutionRecordDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.MissingRangeDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.ObservationAckDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.SyncRequestDto;
import cn.yuanxin.mvp.web.care.CarePlanRepository.CarePlanRow;
import cn.yuanxin.mvp.web.care.CareRecordRepository.Aggregate;
import cn.yuanxin.mvp.web.care.CareRecordRepository.ExistingRecord;
import cn.yuanxin.mvp.web.care.CareRecordRepository.NewRecord;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.BeginOutcome;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import cn.yuanxin.mvp.web.idempotency.IdempotencyHandle;
import cn.yuanxin.mvp.web.idempotency.IdempotencyService;
import cn.yuanxin.mvp.web.idempotency.Jcs;
import cn.yuanxin.mvp.web.idempotency.StaleAttemptException;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/**
 * M4-A05（同步实际状态与有效完成记录）与 M4-A06（确认本地已停止并收尾）编排。
 *
 * <p>事务：T13 begin 与全部外部调用在事务外；最终单短事务锁序 T06→T07（A05 另有
 * DB 判重与批量插入），任何失败整体回滚。记录与汇总账实一致：只有真实新增集合的
 * count_delta 之和 D 参与 K/progress_revision 更新；D=0 不更新。观察合并独立于
 * 记录但同事务；stopped/closed 的生命周期冻结只作用于观察，不阻止迟到记录入账。</p>
 *
 * <p>并发插入竞态用 SAVEPOINT 收敛：唯一约束冲突回滚到保存点后重查判重，
 * 同内容记 duplicate、异内容整批 409 RECORD_CONFLICT，绝不 500。</p>
 */
@Service
public class CareLedgerService {

    private static final Logger log = LoggerFactory.getLogger(CareLedgerService.class);

    public static final String OPERATION_SYNC = "care.observation.sync";
    public static final String OPERATION_CLOSURE = "care.closure.confirm";
    public static final String RESOURCE_TYPE = "care_execution";

    private static final Set<String> OBSERVATION_STATES =
            Set.of("running", "paused", "unknown", "stopped");
    private static final int MISSING_RANGE_LIMIT = 20;
    private static final int GAP_SCAN_LIMIT = 100_001;

    private final CareAuthorization authorization;
    private final CareProjections projections;
    private final CarePlanRepository planRepository;
    private final CareExecutionRepository executionRepository;
    private final CareRecordRepository recordRepository;
    private final IdempotencyService idempotencyService;
    private final TransactionTemplate txTemplate;
    private final ObjectMapper objectMapper;

    public CareLedgerService(CareAuthorization authorization, CareProjections projections,
                             CarePlanRepository planRepository,
                             CareExecutionRepository executionRepository,
                             CareRecordRepository recordRepository,
                             IdempotencyService idempotencyService,
                             TransactionTemplate txTemplate, ObjectMapper objectMapper) {
        this.authorization = authorization;
        this.projections = projections;
        this.planRepository = planRepository;
        this.executionRepository = executionRepository;
        this.recordRepository = recordRepository;
        this.idempotencyService = idempotencyService;
        this.txTemplate = txTemplate;
        this.objectMapper = objectMapper;
    }

    public record SyncOutcome(ObservationAckDto data, boolean replayed) {
    }

    public record ClosureOutcome(ClosureResultDto data, boolean replayed) {
    }

    // ======================= M4-A05 =======================

    public SyncOutcome sync(PrincipalContext principal, UUID executionId, SyncRequestDto request,
                            String idempotencyKey) {
        List<ExecutionRecordDto> records = request.records();
        int n = records.size();
        long[] seqs = new long[n];
        long[] deltas = new long[n];
        Instant[] occurredAts = new Instant[n];
        for (int i = 0; i < n; i++) {
            ExecutionRecordDto r = records.get(i);
            seqs[i] = CareBigints.parse(r.sourceSeq(), "records[" + i + "].sourceSeq");
            if (seqs[i] < 1) {
                throw invalid("records[" + i + "].sourceSeq must be at least 1");
            }
            deltas[i] = CareBigints.parse(r.countDelta(), "records[" + i + "].countDelta");
            if (deltas[i] < 1) {
                throw invalid("records[" + i + "].countDelta must be at least 1");
            }
            occurredAts[i] = parseInstant(r.occurredAt(), "records[" + i + "].occurredAt");
        }
        ExecutionObservationDto observation = request.observation();
        if (observation != null) {
            if (!OBSERVATION_STATES.contains(observation.state())) {
                throw invalid("observation.state is not a supported state");
            }
            CareBigints.parse(observation.seq(), "observation.seq");
            if (observation.verificationRevision() != null) {
                CareBigints.parse(observation.verificationRevision(), "observation.verificationRevision");
            }
            parseInstant(observation.occurredAt(), "observation.occurredAt");
        }

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("observation", observation);
        fields.put("records", records);
        String payloadHash = CanonicalObjectBuilder.forOperation(OPERATION_SYNC)
                .pathParams(Map.of("executionId", executionId.toString()))
                .fields(fields)
                .payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OPERATION_SYNC, idempotencyKey, payloadHash);
        if (outcome instanceof BeginOutcome.ReplaySucceeded replay) {
            return new SyncOutcome(projectSyncReplay(replay, principal), true);
        }
        if (outcome instanceof BeginOutcome.ReplayRejected rejected) {
            throw IdempotencyService.replayedRejection(rejected);
        }
        IdempotencyHandle handle = ((BeginOutcome.NewAttempt) outcome).handle();

        try {
            return runSync(handle, principal, executionId, request, seqs, deltas, occurredAts);
        } catch (ApiException ex) {
            if (deterministic(ex.getCode())) {
                bestEffortReject(handle, ex.getCode(), ex.getMessage(), ex.getDetails());
            }
            throw ex;
        }
    }

    private SyncOutcome runSync(IdempotencyHandle handle, PrincipalContext principal, UUID executionId,
                                SyncRequestDto request, long[] seqs, long[] deltas,
                                Instant[] occurredAts) {
        CareExecutionRow pre = executionRepository.findById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, pre)) {
            throw authorization.notVisible();
        }
        SyncTxResult tx = txTemplate.execute(status -> processSyncTx(status, handle, principal,
                executionId, request, seqs, deltas, occurredAts));
        if (tx == null) {
            throw new ApiException(ErrorCode.INTERNAL, "observation sync produced no result");
        }
        boolean includeProgress = shouldIncludeProgress(principal, tx.plan());
        return new SyncOutcome(new ObservationAckDto(tx.acknowledgements(), tx.status(),
                CareBigints.out(tx.acceptedCount()),
                includeProgress ? projections.progressFor(tx.plan()) : null), false);
    }

    private record SyncTxResult(List<AcknowledgedRecordDto> acknowledgements, String status,
                                long acceptedCount, UUID memberId, CarePlanRow plan) {
    }

    private SyncTxResult processSyncTx(TransactionStatus txStatus, IdempotencyHandle handle,
                                       PrincipalContext principal, UUID executionId,
                                       SyncRequestDto request, long[] seqs, long[] deltas,
                                       Instant[] occurredAts) {
        CareExecutionRow reference = executionRepository.findById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        CarePlanRow plan = planRepository.lockById(reference.planId())
                .orElseThrow(() -> authorization.notVisible());
        CareExecutionRow execution = executionRepository.lockById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, execution)) {
            throw authorization.notVisible();
        }
        String epoch = execution.observationEpoch();

        List<ExecutionRecordDto> records = request.records();
        int n = records.size();
        String[] disposition = new String[n];
        String[] rejectReason = new String[n];
        String[] hashes = new String[n];
        Map<String, String> hashByRecordId = new LinkedHashMap<>();
        Map<String, String[]> seqKeyOwner = new LinkedHashMap<>();
        List<Integer> pending = new ArrayList<>();
        List<String> batchConflicts = new ArrayList<>();

        for (int i = 0; i < n; i++) {
            ExecutionRecordDto r = records.get(i);
            String hash = recordHash(r);
            hashes[i] = hash;
            if (epoch == null || !epoch.equals(r.sourceEpoch())) {
                disposition[i] = "rejected";
                rejectReason[i] = "epoch_mismatch";
                continue;
            }
            String knownHash = hashByRecordId.get(r.recordId());
            if (knownHash != null) {
                if (knownHash.equals(hash)) {
                    disposition[i] = "duplicate";
                } else {
                    batchConflicts.add(r.recordId());
                }
                continue;
            }
            String seqKey = seqKey(r.sourceEpoch(), seqs[i]);
            String[] owner = seqKeyOwner.get(seqKey);
            if (owner != null && (!owner[0].equals(r.recordId()) || !owner[1].equals(hash))) {
                batchConflicts.add(r.recordId());
                continue;
            }
            hashByRecordId.put(r.recordId(), hash);
            seqKeyOwner.put(seqKey, new String[]{r.recordId(), hash});
            pending.add(i);
        }
        if (!batchConflicts.isEmpty()) {
            throw recordConflict(batchConflicts);
        }

        // 两条批量单表 SELECT：client_record_id 集合 / (source_epoch, source_seq) 集合
        List<String> pendingIds = pending.stream().map(i -> records.get(i).recordId()).toList();
        List<String[]> pendingSeqKeys = pending.stream()
                .map(i -> new String[]{records.get(i).sourceEpoch(), Long.toString(seqs[i])})
                .toList();
        Map<String, ExistingRecord> dbById = new LinkedHashMap<>();
        for (ExistingRecord row : recordRepository.findByClientRecordIds(executionId, pendingIds)) {
            dbById.put(row.clientRecordId(), row);
        }
        Map<String, ExistingRecord> dbBySeq = new LinkedHashMap<>();
        for (ExistingRecord row : recordRepository.findBySeqKeys(executionId, pendingSeqKeys)) {
            dbBySeq.put(seqKey(row.sourceEpoch(), row.sourceSeq()), row);
        }

        List<Integer> toInsert = new ArrayList<>();
        List<String> dbConflicts = new ArrayList<>();
        for (int i : pending) {
            ExecutionRecordDto r = records.get(i);
            ExistingRecord byId = dbById.get(r.recordId());
            ExistingRecord bySeq = dbBySeq.get(seqKey(r.sourceEpoch(), seqs[i]));
            boolean conflict = (byId != null && !byId.payloadHash().equals(hashes[i]))
                    || (bySeq != null && (!bySeq.clientRecordId().equals(r.recordId())
                            || !bySeq.payloadHash().equals(hashes[i])));
            if (conflict) {
                dbConflicts.add(r.recordId());
            } else if (byId != null || bySeq != null) {
                disposition[i] = "duplicate";
            } else {
                toInsert.add(i);
            }
        }
        if (!dbConflicts.isEmpty()) {
            throw recordConflict(dbConflicts);
        }

        Instant receivedAt = Instant.now();
        long delta = 0L;
        long insertedCount = 0L;
        long batchMaxSourceSeq = 0L;
        for (int i : toInsert) {
            ExecutionRecordDto r = records.get(i);
            Object savepoint = txStatus.createSavepoint();
            boolean inserted = false;
            try {
                recordRepository.insert(new NewRecord(UUID.randomUUID(), executionId, r.recordId(),
                        execution.planId(), execution.memberId(), execution.microcrystalId(),
                        deltas[i], r.sourceEpoch(), seqs[i], occurredAts[i], receivedAt, hashes[i],
                        recordPayload(r)));
                inserted = true;
            } catch (DuplicateKeyException race) {
                txStatus.rollbackToSavepoint(savepoint);
                ExistingRecord byId = firstOf(recordRepository.findByClientRecordIds(executionId,
                        List.of(r.recordId())));
                ExistingRecord bySeq = firstOf(recordRepository.findBySeqKeys(executionId,
                        List.<String[]>of(new String[]{r.sourceEpoch(), Long.toString(seqs[i])})));
                boolean conflict = (byId != null && !byId.payloadHash().equals(hashes[i]))
                        || (bySeq != null && (!bySeq.clientRecordId().equals(r.recordId())
                                || !bySeq.payloadHash().equals(hashes[i])));
                if (conflict) {
                    throw recordConflict(List.of(r.recordId()));
                }
                disposition[i] = "duplicate";
            } finally {
                txStatus.releaseSavepoint(savepoint);
            }
            if (inserted) {
                delta = addChecked(delta, deltas[i]);
                disposition[i] = "accepted";
                insertedCount++;
                batchMaxSourceSeq = Math.max(batchMaxSourceSeq, seqs[i]);
            }
        }

        if (delta > 0) {
            addChecked(plan.completedCount(), delta); // 溢出预检（400 count_overflow）
            int planRows = planRepository.addCompletedCount(plan.id(), delta, receivedAt);
            if (planRows != 1) {
                throw new ApiException(ErrorCode.INTERNAL,
                        "care plan ledger update affected " + planRows + " rows");
            }
            int executionRows = executionRepository.addAcceptedCount(executionId, delta, receivedAt);
            if (executionRows != 1) {
                throw new ApiException(ErrorCode.INTERNAL,
                        "care execution ledger update affected " + executionRows + " rows");
            }
        }
        if ("closed".equals(execution.status()) && insertedCount > 0) {
            // 迟到差异留痕：仅对已关闭执行，只增 late_variance，不动 status/closed_at
            executionRepository.applyLateVariance(executionId, insertedCount, batchMaxSourceSeq,
                    receivedAt);
            log.warn("late care records admitted to closed execution {}: records={}, maxSourceSeq={}",
                    executionId, insertedCount, batchMaxSourceSeq);
        }

        String status = execution.status();
        Long lastObservationSeq = execution.lastObservationSeq();
        String latestObservationJson = execution.latestObservation();
        Instant stoppedAt = null;
        boolean observationChanged = false;

        ExecutionObservationDto observation = request.observation();
        if (observation != null) {
            long obsSeq = CareBigints.parse(observation.seq(), "observation.seq");
            if (epoch == null || !epoch.equals(observation.epoch())) {
                throw new ApiException(ErrorCode.RECORD_CONFLICT,
                        "observation epoch does not match the execution stream",
                        Map.of("reason", "observation_epoch_mismatch"));
            }
            if (lastObservationSeq == null || obsSeq > lastObservationSeq) {
                // 生命周期冻结：stopped/closed 不接受更高序号观察（记录已入账）
                if (!"stopped".equals(execution.status()) && !"closed".equals(execution.status())) {
                    boolean invalidated = observationInvalidated(execution.latestObservation(),
                            observation);
                    status = stateMachineStatus(execution, observation, invalidated);
                    lastObservationSeq = obsSeq;
                    latestObservationJson = buildObservationJson(observation, obsSeq, invalidated);
                    observationChanged = true;
                    if ("stopped".equals(status)) {
                        stoppedAt = parseInstant(observation.occurredAt(), "observation.occurredAt");
                    }
                }
            } else if (obsSeq == lastObservationSeq) {
                if (!observationMatches(execution.latestObservation(), observation)) {
                    throw new ApiException(ErrorCode.RECORD_CONFLICT,
                            "observation seq reused with different content",
                            Map.of("reason", "observation_seq_conflict"));
                }
            }
            // obsSeq < last：乱序旧观察静默忽略，同批记录仍入账
        }
        if (observationChanged) {
            int rows = executionRepository.updateObservation(executionId, lastObservationSeq,
                    latestObservationJson, status, stoppedAt, receivedAt);
            if (rows != 1) {
                throw new ApiException(ErrorCode.INTERNAL,
                        "care execution observation update affected " + rows + " rows");
            }
        }

        long acceptedCount = execution.acceptedCount() + delta;
        CarePlanRow progressPlan = delta > 0
                ? planRepository.findById(plan.id()).orElse(plan) : plan;

        List<AcknowledgedRecordDto> acknowledgements = new ArrayList<>();
        List<Map<String, Object>> summaryAcks = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            String dispositionValue = disposition[i] == null ? "duplicate" : disposition[i];
            acknowledgements.add(new AcknowledgedRecordDto(records.get(i).recordId(),
                    dispositionValue, rejectReason[i]));
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("record_id", records.get(i).recordId());
            entry.put("disposition", dispositionValue);
            if (rejectReason[i] != null) {
                entry.put("reject_reason", rejectReason[i]);
            }
            summaryAcks.add(entry);
        }
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("acknowledgements", summaryAcks);
        summary.put("accepted_count", Long.toString(acceptedCount));
        summary.put("execution_status", status);
        idempotencyService.completeSuccess(handle, RESOURCE_TYPE, executionId, summary);
        return new SyncTxResult(acknowledgements, status, acceptedCount, execution.memberId(),
                progressPlan);
    }

    private ObservationAckDto projectSyncReplay(BeginOutcome.ReplaySucceeded replay,
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
        boolean includeProgress = shouldIncludeProgress(principal, plan);
        return new ObservationAckDto(frozenAcknowledgements(replay.resultSummary()), row.status(),
                CareBigints.out(row.acceptedCount()),
                includeProgress ? projections.progressFor(plan) : null);
    }

    private List<AcknowledgedRecordDto> frozenAcknowledgements(JsonNode resultSummary) {
        List<AcknowledgedRecordDto> acknowledgements = new ArrayList<>();
        JsonNode array = resultSummary == null ? null : resultSummary.path("acknowledgements");
        if (array == null || !array.isArray()) {
            return acknowledgements;
        }
        for (JsonNode node : array) {
            String recordId = node.path("record_id").asText(null);
            String disposition = node.path("disposition").asText(null);
            if (recordId == null || disposition == null) {
                continue;
            }
            JsonNode reject = node.get("reject_reason");
            acknowledgements.add(new AcknowledgedRecordDto(recordId, disposition,
                    reject == null || reject.isNull() ? null : reject.asText()));
        }
        return acknowledgements;
    }

    // ======================= M4-A06 =======================

    public ClosureOutcome close(PrincipalContext principal, UUID executionId,
                                ClosureRequestDto request, String idempotencyKey) {
        long stopObservationSeq = CareBigints.parse(request.stopObservationSeq(),
                "stopObservationSeq");
        long finalRecordSeq = CareBigints.parse(request.finalRecordSeq(), "finalRecordSeq");
        long finalCount = CareBigints.parse(request.finalCount(), "finalCount");

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("stopObservationSeq", request.stopObservationSeq());
        fields.put("reason", request.reason());
        fields.put("recordStreamEpoch", request.recordStreamEpoch());
        fields.put("finalRecordSeq", request.finalRecordSeq());
        fields.put("finalCount", request.finalCount());
        String payloadHash = CanonicalObjectBuilder.forOperation(OPERATION_CLOSURE)
                .pathParams(Map.of("executionId", executionId.toString()))
                .fields(fields)
                .payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OPERATION_CLOSURE, idempotencyKey, payloadHash);
        if (outcome instanceof BeginOutcome.ReplaySucceeded replay) {
            return new ClosureOutcome(projectClosureReplay(replay, principal), true);
        }
        if (outcome instanceof BeginOutcome.ReplayRejected rejected) {
            throw IdempotencyService.replayedRejection(rejected);
        }
        IdempotencyHandle handle = ((BeginOutcome.NewAttempt) outcome).handle();

        try {
            return runClosure(handle, principal, executionId, request, stopObservationSeq,
                    finalRecordSeq, finalCount);
        } catch (ApiException ex) {
            if (deterministic(ex.getCode())) {
                bestEffortReject(handle, ex.getCode(), ex.getMessage(), ex.getDetails());
            }
            throw ex;
        }
    }

    private ClosureOutcome runClosure(IdempotencyHandle handle, PrincipalContext principal,
                                      UUID executionId, ClosureRequestDto request,
                                      long stopObservationSeq, long finalRecordSeq,
                                      long finalCount) {
        CareExecutionRow pre = executionRepository.findById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, pre)) {
            throw authorization.notVisible();
        }
        Instant closedAt = txTemplate.execute(status -> processClosureTx(handle, principal,
                executionId, request, stopObservationSeq, finalRecordSeq, finalCount));
        if (closedAt == null) {
            throw new ApiException(ErrorCode.INTERNAL, "closure produced no result");
        }
        return new ClosureOutcome(new ClosureResultDto(Boolean.TRUE, rfc3339(closedAt),
                Boolean.TRUE), false);
    }

    private Instant processClosureTx(IdempotencyHandle handle, PrincipalContext principal,
                                     UUID executionId, ClosureRequestDto request,
                                     long stopObservationSeq, long finalRecordSeq, long finalCount) {
        CareExecutionRow reference = executionRepository.findById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        planRepository.lockById(reference.planId())
                .orElseThrow(() -> authorization.notVisible());
        CareExecutionRow execution = executionRepository.lockById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, execution)) {
            throw authorization.notVisible();
        }
        if ("closed".equals(execution.status())) {
            throw executionNotResumable("already_closed");
        }
        if (!"stopped".equals(execution.status())) {
            throw stopNotConfirmed("not_stopped");
        }
        if (!Objects.equals(execution.observationEpoch(), request.recordStreamEpoch())) {
            throw new ApiException(ErrorCode.RECORD_CONFLICT,
                    "record stream epoch does not match the execution stream",
                    Map.of("reason", "epoch_mismatch"));
        }
        if (execution.lastObservationSeq() == null
                || execution.lastObservationSeq() != stopObservationSeq
                || !"stopped".equals(observationState(execution.latestObservation()))) {
            throw stopNotConfirmed("stop_observation_mismatch");
        }

        String epoch = execution.observationEpoch();
        Aggregate aggregate = recordRepository.aggregate(executionId, epoch);
        if (aggregate.maxSeq() > finalRecordSeq) {
            throw closureGaps("max_seq_exceeds_final", null, false, null, null);
        }
        if (aggregate.recordCount() != finalRecordSeq) {
            GapReport gaps = aggregate.recordCount() < finalRecordSeq && aggregate.maxSeq() <= finalRecordSeq
                    ? missingRanges(executionId, epoch, finalRecordSeq)
                    : new GapReport(List.of(), true);
            throw closureGaps("gaps", gaps.ranges(), gaps.more(), null, null);
        }
        if (aggregate.totalCount() != finalCount) {
            throw closureGaps("count_mismatch", null, false, request.finalCount(),
                    CareBigints.out(aggregate.totalCount()));
        }

        Instant now = Instant.now();
        String manifest = writeJson(buildClosureManifest(execution, request, finalRecordSeq,
                aggregate, now));
        int rows = executionRepository.close(executionId, now, manifest);
        if (rows == 0) {
            throw executionNotResumable("already_closed");
        }
        idempotencyService.completeSuccess(handle, RESOURCE_TYPE, executionId, Map.of(
                "closed", Boolean.TRUE,
                "closed_at", rfc3339(now),
                "occupancy_released", Boolean.TRUE));
        return now;
    }

    private ClosureResultDto projectClosureReplay(BeginOutcome.ReplaySucceeded replay,
                                                  PrincipalContext principal) {
        if (!RESOURCE_TYPE.equals(replay.resourceType()) || replay.resourceId() == null) {
            throw new ApiException(ErrorCode.INTERNAL, "unexpected replay resource");
        }
        CareExecutionRow row = executionRepository.findById(replay.resourceId())
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.isOriginalController(principal, row)) {
            throw authorization.notVisible();
        }
        boolean closed = row.closedAt() != null;
        return new ClosureResultDto(closed, row.closedAt() == null ? null : rfc3339(row.closedAt()),
                Boolean.TRUE);
    }

    private record GapReport(List<MissingRangeDto> ranges, boolean more) {
    }

    private GapReport missingRanges(UUID executionId, String epoch, long finalRecordSeq) {
        List<Long> seqs = recordRepository.sourceSeqsUpTo(executionId, epoch, finalRecordSeq,
                GAP_SCAN_LIMIT);
        boolean more = seqs.size() >= GAP_SCAN_LIMIT;
        List<MissingRangeDto> ranges = new ArrayList<>();
        long expected = 1L;
        boolean maxReached = false;
        for (long seq : seqs) {
            while (expected < seq) {
                if (ranges.size() >= MISSING_RANGE_LIMIT) {
                    more = true;
                    break;
                }
                ranges.add(new MissingRangeDto(Long.toString(expected), Long.toString(seq - 1)));
                expected = seq;
            }
            if (more) {
                break;
            }
            if (seq == Long.MAX_VALUE) {
                maxReached = true;
                expected = Long.MAX_VALUE;
                break;
            }
            expected = seq + 1;
        }
        // 尾段直接以 finalRecordSeq 为右端（绝不计算 W+1）；达到 MAX 或已截断则不追加
        if (!more && !maxReached && expected <= finalRecordSeq) {
            if (ranges.size() >= MISSING_RANGE_LIMIT) {
                more = true;
            } else {
                ranges.add(new MissingRangeDto(Long.toString(expected),
                        Long.toString(finalRecordSeq)));
            }
        }
        return new GapReport(ranges, more);
    }

    private JsonNode buildClosureManifest(CareExecutionRow execution, ClosureRequestDto request,
                                          long finalRecordSeq, Aggregate aggregate, Instant now) {
        ObjectNode manifest = objectMapper.createObjectNode();
        manifest.put("schema_version", 1);
        manifest.put("record_stream_epoch", execution.observationEpoch());
        manifest.put("final_record_seq", Long.toString(finalRecordSeq));
        manifest.put("final_count", request.finalCount());
        manifest.put("stop_observation_seq", CareBigints.out(execution.lastObservationSeq()));
        String stopOccurredAt = observationOccurredAt(execution.latestObservation());
        manifest.put("stop_occurred_at", stopOccurredAt);
        manifest.put("confirmed_at", rfc3339(now));
        manifest.put("record_count", Long.toString(aggregate.recordCount()));
        manifest.put("total_count", CareBigints.out(aggregate.totalCount()));
        manifest.put("reason", request.reason());
        return manifest;
    }

    // ======================= observation helpers =======================

    private String stateMachineStatus(CareExecutionRow execution, ExecutionObservationDto observation,
                                      boolean invalidated) {
        String current = execution.status();
        return switch (observation.state()) {
            case "paused" -> "paused";
            case "unknown" -> "unknown";
            case "stopped" -> "stopped";
            case "running" -> {
                if ("running".equals(current)) {
                    yield "running";
                }
                if (!"admitted".equals(current) && !"paused".equals(current)) {
                    yield current; // unknown 等禁止 →running
                }
                // admitted/paused 统一门控：连续性未失效、本轮未声明失效、核验代次匹配
                boolean continuityOk = observation.continuityValid() == null
                        || observation.continuityValid();
                boolean revisionOk = observation.verificationRevision() == null
                        || CareBigints.parse(observation.verificationRevision(),
                                "verificationRevision") == execution.verificationRevision();
                yield !invalidated && continuityOk && revisionOk ? "running" : current;
            }
            default -> current;
        };
    }

    private boolean observationInvalidated(String latestObservationJson,
                                           ExecutionObservationDto observation) {
        if (observation.continuityValid() != null && !observation.continuityValid()) {
            return true;
        }
        JsonNode node = readJsonObject(latestObservationJson);
        return node != null && node.path("continuity_invalidated").asBoolean(false);
    }

    private String buildObservationJson(ExecutionObservationDto observation, long seq,
                                        boolean invalidated) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("schema_version", 1);
        node.put("epoch", observation.epoch());
        node.put("seq", Long.toString(seq));
        node.put("state", observation.state());
        node.put("occurred_at", rfc3339(parseInstant(observation.occurredAt(),
                "observation.occurredAt")));
        if (observation.verificationRevision() != null) {
            node.put("verification_revision", observation.verificationRevision());
        }
        if (observation.continuityValid() != null) {
            node.put("continuity_valid", observation.continuityValid());
        }
        node.put("continuity_invalidated", invalidated);
        return node.toString();
    }

    private boolean observationMatches(String latestObservationJson,
                                       ExecutionObservationDto observation) {
        JsonNode node = readJsonObject(latestObservationJson);
        if (node == null) {
            return false;
        }
        String storedState = node.path("state").asText(null);
        String storedOccurredAt = node.path("occurred_at").asText(null);
        String incomingOccurredAt = rfc3339(parseInstant(observation.occurredAt(),
                "observation.occurredAt"));
        Boolean storedContinuity = node.has("continuity_valid")
                ? node.get("continuity_valid").booleanValue() : null;
        String storedRevision = node.has("verification_revision")
                ? node.get("verification_revision").asText() : null;
        return Objects.equals(storedState, observation.state())
                && Objects.equals(storedOccurredAt, incomingOccurredAt)
                && Objects.equals(storedContinuity, observation.continuityValid())
                && Objects.equals(storedRevision, observation.verificationRevision());
    }

    private String observationState(String latestObservationJson) {
        JsonNode node = readJsonObject(latestObservationJson);
        return node == null ? null : node.path("state").asText(null);
    }

    private String observationOccurredAt(String latestObservationJson) {
        JsonNode node = readJsonObject(latestObservationJson);
        return node == null ? null : node.path("occurred_at").asText(null);
    }

    // ======================= record helpers =======================

    private String recordHash(ExecutionRecordDto r) {
        Map<String, Object> hashFields = new LinkedHashMap<>();
        hashFields.put("recordId", r.recordId());
        hashFields.put("sourceEpoch", r.sourceEpoch());
        hashFields.put("sourceSeq", r.sourceSeq());
        hashFields.put("countDelta", r.countDelta());
        hashFields.put("occurredAt", r.occurredAt());
        return Jcs.sha256HexOfObject(hashFields);
    }

    private String recordPayload(ExecutionRecordDto r) {
        ObjectNode payload = objectMapper.createObjectNode();
        payload.put("schema_version", 1);
        payload.put("record_id", r.recordId());
        payload.put("source_epoch", r.sourceEpoch());
        payload.put("source_seq", r.sourceSeq());
        payload.put("count_delta", r.countDelta());
        payload.put("occurred_at", r.occurredAt());
        return payload.toString();
    }

    private static String seqKey(String epoch, long seq) {
        return epoch + "|" + seq;
    }

    private static ExistingRecord firstOf(List<ExistingRecord> rows) {
        return rows.isEmpty() ? null : rows.get(0);
    }

    // ======================= shared helpers =======================

    /**
     * Progress 需要<b>当前</b>方案读取资格（APP active 授权 / 云台当前任务指针），
     * 而非永久原控制端；不具备时 progress=null，但最小确认信息仍 200。
     */
    private boolean shouldIncludeProgress(PrincipalContext principal, CarePlanRow plan) {
        return authorization.hasPlanReadEligibility(principal, plan);
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
            // 已被接管/已完成：保留既有结果
        } catch (RuntimeException failure) {
            log.warn("best-effort idempotency rejection failed: {}", failure.getMessage());
        }
    }

    private static boolean deterministic(ErrorCode code) {
        return switch (code) {
            case DEPENDENCY_UNAVAILABLE, DEPENDENCY_TIMEOUT, REQUEST_IN_PROGRESS, RATE_LIMITED,
                 INTERNAL, NOT_IMPLEMENTED, UNSUPPORTED_CONTRACT -> false;
            default -> true;
        };
    }

    private static long addChecked(long left, long right) {
        try {
            return Math.addExact(left, right);
        } catch (ArithmeticException overflow) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "accepted count overflow",
                    Map.of("reason", "count_overflow"));
        }
    }

    private static ApiException recordConflict(List<String> conflicts) {
        List<String> bounded = conflicts.stream().distinct().limit(20).toList();
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("conflictingRecordIds", bounded);
        details.put("totalConflicts", conflicts.size());
        return new ApiException(ErrorCode.RECORD_CONFLICT,
                "record batch conflicts with duplicate or existing content", details);
    }

    private static ApiException stopNotConfirmed(String reason) {
        return new ApiException(ErrorCode.STOP_NOT_CONFIRMED, "care execution stop is not confirmed",
                Map.of("reason", reason));
    }

    private static ApiException executionNotResumable(String reason) {
        return new ApiException(ErrorCode.EXECUTION_NOT_RESUMABLE, "care execution is not resumable",
                Map.of("reason", reason));
    }

    private static ApiException closureGaps(String reason, List<MissingRangeDto> ranges, boolean more,
                                            String finalCount, String totalCount) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("reason", reason);
        if (ranges != null) {
            details.put("missingRanges", ranges);
            details.put("more", more);
        }
        if (finalCount != null) {
            details.put("finalCount", finalCount);
        }
        if (totalCount != null) {
            details.put("totalCount", totalCount);
        }
        return new ApiException(ErrorCode.CLOSURE_GAPS,
                "care execution closure has reconciliation gaps", details);
    }

    private JsonNode readJsonObject(String raw) {
        if (raw == null || raw.isBlank() || "{}".equals(raw.trim())) {
            return null;
        }
        try {
            JsonNode node = objectMapper.readTree(raw);
            return node != null && node.isObject() && node.size() > 0 ? node : null;
        } catch (Exception parseFailure) {
            return null;
        }
    }

    private String writeJson(JsonNode node) {
        try {
            return objectMapper.writeValueAsString(node);
        } catch (JsonProcessingException serializationFailure) {
            throw new ApiException(ErrorCode.INTERNAL, "ledger projection serialization failed");
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
}

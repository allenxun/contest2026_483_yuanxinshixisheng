package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.care.CareExecutionRepository.CareExecutionRow;
import cn.yuanxin.mvp.web.care.CarePlanRepository.CarePlanRow;
import cn.yuanxin.mvp.web.care.CareProjections.CareExecutionListItem;
import cn.yuanxin.mvp.web.care.CareProjections.CareExecutionView;
import cn.yuanxin.mvp.web.care.CareProjections.CarePlanFullView;
import cn.yuanxin.mvp.web.care.CareProjections.CarePlanListItem;
import cn.yuanxin.mvp.web.care.CareProjections.Progress;
import cn.yuanxin.mvp.web.care.CareProjections.ProgressWithSync;
import cn.yuanxin.mvp.web.care.CareProjections.RecordWatermark;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.CursorCodec;
import cn.yuanxin.mvp.web.web.CursorException;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.ListData;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.UUID;

/**
 * M4 查询编排（A01/A02/A07/A08/A09）：授权判定 + 单表仓储分页 + 投影。
 * 全部端点零写入、查询不增加 K、不改变执行状态。
 */
@Service
public class CareQueryService {

    private final CareAuthorization authorization;
    private final CareProjections projections;
    private final CarePlanRepository planRepository;
    private final CareExecutionRepository executionRepository;
    private final CareRecordRepository recordRepository;
    private final AssessmentReadRepository assessmentRepository;
    private final GimbalReadRepository gimbalRepository;
    private final CursorCodec cursorCodec;

    public CareQueryService(CareAuthorization authorization, CareProjections projections,
                            CarePlanRepository planRepository,
                            CareExecutionRepository executionRepository,
                            CareRecordRepository recordRepository,
                            AssessmentReadRepository assessmentRepository,
                            GimbalReadRepository gimbalRepository, CursorCodec cursorCodec) {
        this.authorization = authorization;
        this.projections = projections;
        this.planRepository = planRepository;
        this.executionRepository = executionRepository;
        this.recordRepository = recordRepository;
        this.assessmentRepository = assessmentRepository;
        this.gimbalRepository = gimbalRepository;
        this.cursorCodec = cursorCodec;
    }

    private record CursorKey(Instant sortValue, UUID id) {
    }

    // ---------- M4-A01 ----------

    public ListData<CarePlanListItem> listMemberCarePlans(PrincipalContext principal, UUID memberId,
                                                          UUID reportId, Integer limit, String cursor) {
        authorization.requireApp(principal);
        int pageSize = cursorCodec.normalizeLimit(limit);
        String digest = "reportId=" + (reportId == null ? "" : reportId);
        CursorKey key = decodeCursorOrNull(cursor, digest);
        if (!authorization.hasActiveGrant(principal, memberId)) {
            throw authorization.notVisible();
        }
        UUID assessmentId = null;
        if (reportId != null) {
            var ref = assessmentRepository.findByReportId(reportId);
            if (ref.isEmpty() || !memberId.equals(ref.get().memberId())) {
                return new ListData<>(List.of(), null); // 无行/他人报告 → 空页，不泄露
            }
            assessmentId = ref.get().id();
        }
        List<CarePlanRow> rows = planRepository.pageByMember(memberId, assessmentId,
                key == null ? null : key.sortValue(), key == null ? null : key.id(), pageSize + 1);
        boolean hasNext = rows.size() > pageSize;
        List<CarePlanRow> page = hasNext ? rows.subList(0, pageSize) : rows;
        List<CarePlanListItem> items = page.stream().map(this::toPlanItem).toList();
        String nextCursor = hasNext && !page.isEmpty()
                ? encodeCursor(page.get(page.size() - 1), digest) : null;
        return new ListData<>(items, nextCursor);
    }

    private CarePlanListItem toPlanItem(CarePlanRow row) {
        Progress progress = null;
        if ("ready".equals(row.generationStatus())) {
            requireTargetCount(row);
            progress = projections.progressFor(row);
        }
        return new CarePlanListItem(row.id().toString(), row.generationStatus(),
                projections.planSummaryOrNull(row.planSummary()), progress);
    }

    // ---------- M4-A02 ----------

    public CarePlanFullView getCarePlan(PrincipalContext principal, UUID planId, String view) {
        authorization.requireApp(principal);
        if (view != null && !"full".equals(view)) {
            throw new ApiException(ErrorCode.INVALID_INPUT, "view must be full");
        }
        CarePlanRow row = planRepository.findById(planId)
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.hasActiveGrant(principal, row.memberId())) {
            throw authorization.notVisible();
        }
        String status = row.generationStatus();
        if ("ready".equals(status)) {
            requireTargetCount(row);
            Object plan = projections.planPayloadOrNull(row.planPayload());
            if (plan == null) {
                // DB CHECK 应阻止：ready 必须有 plan_payload（防御）
                throw new ApiException(ErrorCode.INTERNAL, "ready care plan missing payload");
            }
            return new CarePlanFullView(row.id().toString(), status, plan,
                    projections.progressFor(row), null);
        }
        String waitingReason = switch (status) {
            case "waiting_inputs" -> "waiting_inputs";
            case "generating" -> "generating";
            case "failed" -> "generation_failed";
            default -> null;
        };
        return new CarePlanFullView(row.id().toString(), status, null, null, waitingReason);
    }

    // ---------- M4-A07 ----------

    public CareExecutionView getCareExecution(PrincipalContext principal, UUID executionId,
                                              String recordsAfterSeq, Integer limit) {
        int pageSize = cursorCodec.normalizeLimit(limit);
        Long afterSeq = CareBigints.parseNullable(recordsAfterSeq, "recordsAfterSeq");
        CareExecutionRow row = executionRepository.findById(executionId)
                .orElseThrow(() -> authorization.notVisible());
        boolean authorizedViewer = authorization.hasActiveGrant(principal, row.memberId());
        boolean originalController = authorization.isOriginalController(principal, row);
        if (!authorizedViewer && !originalController) {
            throw authorization.notVisible();
        }
        long maxSourceSeq = recordRepository.maxSourceSeq(row.id(), row.observationEpoch());
        RecordWatermark watermark = projections.recordWatermark(row, maxSourceSeq);
        List<String> acknowledged = afterSeq == null ? null
                : recordRepository.clientRecordIdsAfter(row.id(), row.observationEpoch(), afterSeq, pageSize);
        if (authorizedViewer) {
            Progress progress = planRepository.findById(row.planId())
                    .map(projections::progressFor).orElse(null);
            return new CareExecutionView(row.id().toString(), row.status(),
                    projections.controllerRef(row), row.memberId().toString(),
                    row.planId().toString(), row.microcrystalId().toString(),
                    CareBigints.out(row.acceptedCount()),
                    projections.executionObservation(row.latestObservation()),
                    watermark, acknowledged, rfc3339(row.closedAt()), progress);
        }
        // 仅原控制端（含云台）→ 最小对账视图，其余字段 null
        return new CareExecutionView(row.id().toString(), row.status(), null, null, null, null,
                CareBigints.out(row.acceptedCount()), null, watermark, acknowledged,
                rfc3339(row.closedAt()), null);
    }

    // ---------- M4-A08 ----------

    public ProgressWithSync getPlanProgress(PrincipalContext principal, UUID planId,
                                            String executionIdRaw, String verificationRevision) {
        if (principal.principalType() == PrincipalType.GIMBAL) {
            if (executionIdRaw == null || verificationRevision == null) {
                throw new ApiException(ErrorCode.INVALID_INPUT,
                        "executionId and verificationRevision are required for gimbal callers");
            }
            UUID executionId = parseUuid(executionIdRaw, "executionId");
            long providedRevision = CareBigints.parse(verificationRevision, "verificationRevision");
            CareExecutionRow execution = executionRepository.findById(executionId)
                    .orElseThrow(() -> authorization.notVisible());
            if (execution.controllerGimbalId() == null
                    || !execution.controllerGimbalId().equals(principal.gimbalUuid())) {
                throw authorization.notVisible();
            }
            if (!execution.planId().equals(planId)) {
                throw authorization.notVisible();
            }
            if (execution.verificationRevision() != providedRevision) {
                throw authorization.notVisible(); // 过期核验不开放
            }
            CarePlanRow plan = planRepository.findById(planId)
                    .orElseThrow(() -> authorization.notVisible());
            if (!"ready".equals(plan.generationStatus())) {
                throw new ApiException(ErrorCode.PLAN_NOT_READY, "care plan is not ready");
            }
            GimbalReadRepository.GimbalPointer pointer = gimbalRepository
                    .findPointer(principal.gimbalUuid())
                    .orElseThrow(() -> authorization.notVisible());
            if (pointer.currentAssessmentId() == null
                    || !pointer.currentAssessmentId().equals(plan.assessmentId())) {
                throw new ApiException(ErrorCode.TASK_REPLACED, "gimbal current assessment was replaced");
            }
            return projections.progressWithSync(plan);
        }
        // APP：忽略 executionId/verificationRevision
        CarePlanRow plan = planRepository.findById(planId)
                .orElseThrow(() -> authorization.notVisible());
        if (!authorization.hasActiveGrant(principal, plan.memberId())) {
            throw authorization.notVisible();
        }
        if (!"ready".equals(plan.generationStatus())) {
            throw new ApiException(ErrorCode.PLAN_NOT_READY, "care plan is not ready");
        }
        return projections.progressWithSync(plan);
    }

    // ---------- M4-A09 ----------

    public ListData<CareExecutionListItem> listMemberCareExecutions(PrincipalContext principal,
                                                                    UUID memberId, UUID planId,
                                                                    String fromRaw, String toRaw,
                                                                    Integer limit, String cursor) {
        authorization.requireApp(principal);
        int pageSize = cursorCodec.normalizeLimit(limit);
        Instant from = parseInstant(fromRaw, "from");
        Instant to = parseInstant(toRaw, "to");
        String digest = "planId=" + (planId == null ? "" : planId)
                + ";from=" + (from == null ? "" : from)
                + ";to=" + (to == null ? "" : to);
        CursorKey key = decodeCursorOrNull(cursor, digest);
        if (!authorization.hasActiveGrant(principal, memberId)) {
            throw authorization.notVisible();
        }
        List<CareExecutionRow> rows = executionRepository.pageByMember(memberId, planId,
                from, to, key == null ? null : key.sortValue(), key == null ? null : key.id(),
                pageSize + 1);
        boolean hasNext = rows.size() > pageSize;
        List<CareExecutionRow> page = hasNext ? rows.subList(0, pageSize) : rows;
        List<CareExecutionListItem> items = page.stream()
                .map(row -> new CareExecutionListItem(row.id().toString(), row.status(),
                        rfc3339(row.createdAt()), rfc3339(row.closedAt()),
                        CareBigints.out(row.acceptedCount()),
                        projections.planSnapshotSummaryOrNull(row.planSnapshot())))
                .toList();
        String nextCursor = hasNext && !page.isEmpty()
                ? encodeCursor(page.get(page.size() - 1), digest) : null;
        return new ListData<>(items, nextCursor);
    }

    // ---------- helpers ----------

    private static void requireTargetCount(CarePlanRow row) {
        if (row.targetCount() == null) {
            // DB CHECK (ready ⇒ target_count>0) 应阻止；防御性 500
            throw new ApiException(ErrorCode.INTERNAL, "ready care plan missing target count");
        }
    }

    private CursorKey decodeCursorOrNull(String cursor, String filterDigest) {
        if (cursor == null || cursor.isBlank()) {
            return null;
        }
        CursorCodec.Cursor decoded = cursorCodec.decode(cursor);
        if (!filterDigest.equals(decoded.filterDigest())) {
            throw new CursorException("cursor does not match the current query filters");
        }
        try {
            return new CursorKey(Instant.parse(decoded.sortValue()), UUID.fromString(decoded.id()));
        } catch (RuntimeException invalid) {
            throw new CursorException("cursor is not a valid opaque token");
        }
    }

    private String encodeCursor(CarePlanRow row, String filterDigest) {
        return cursorCodec.encode(row.createdAt().toString(), row.id().toString(), filterDigest);
    }

    private String encodeCursor(CareExecutionRow row, String filterDigest) {
        return cursorCodec.encode(row.createdAt().toString(), row.id().toString(), filterDigest);
    }

    private static String rfc3339(Instant instant) {
        return instant == null ? null : EnvelopeSupport.rfc3339(instant);
    }

    private static Instant parseInstant(String raw, String field) {
        if (raw == null) {
            return null;
        }
        try {
            return Instant.parse(raw);
        } catch (DateTimeParseException invalid) {
            throw new ApiException(ErrorCode.INVALID_INPUT,
                    field + " must be an RFC3339 date-time");
        }
    }

    private static UUID parseUuid(String raw, String field) {
        try {
            return UUID.fromString(raw);
        } catch (IllegalArgumentException invalid) {
            throw new ApiException(ErrorCode.INVALID_INPUT, field + " must be a UUID");
        }
    }
}

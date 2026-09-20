package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.assessments.AssessmentMultipartParser.A01Metadata;
import cn.yuanxin.mvp.web.assessments.AssessmentMultipartParser.A02Metadata;
import cn.yuanxin.mvp.web.assessments.AssessmentMultipartParser.ParsedA01;
import cn.yuanxin.mvp.web.assessments.AssessmentMultipartParser.ParsedA02;
import cn.yuanxin.mvp.web.assessments.dto.AssessmentTaskAccepted;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.BeginOutcome;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import cn.yuanxin.mvp.web.idempotency.IdempotencyHandle;
import cn.yuanxin.mvp.web.idempotency.IdempotencyService;
import cn.yuanxin.mvp.web.jobs.JobEnqueuer;
import cn.yuanxin.mvp.web.media.MediaIntakeService;
import cn.yuanxin.mvp.web.media.MediaPurpose;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/**
 * M3-A01 受理 / M3-A02 补拍应用服务（DD 5、7.1、8.1/8.2、9.1）。
 *
 * <p>接线：multipart 解析 → canonicalObject → T13 begin（事务外）→ T11
 * ingest（事务外）→ 业务事务（锁 T03 → 查 T07 占用 → 插/更 T05 → 换指针 →
 * 补 T11 归属 → 入队 T12 → T13 complete）。确定性业务拒绝在事务内写 T13
 * rejected 并提交，异常在提交后抛出（绝不从事务回调内抛拒绝异常）。</p>
 */
@Service
public class AssessmentAcceptanceService {

    public static final String OPERATION_A01 = "m3a01";
    public static final String OPERATION_A02 = "m3a02";
    public static final String JOB_TYPE = "assessment.analyze";

    private final IdempotencyService idempotencyService;
    private final MediaIntakeService mediaIntakeService;
    private final JobEnqueuer jobEnqueuer;
    private final TransactionTemplate txTemplate;
    private final AssessmentRepository assessmentRepository;
    private final AssessmentGimbalRepository gimbalRepository;
    private final AssessmentMediaRepository mediaRepository;
    private final AssessmentAccessRepository accessRepository;
    private final PhotoVersions photoVersions;
    private final MediaCleanupEnqueuer mediaCleanupEnqueuer;

    public AssessmentAcceptanceService(IdempotencyService idempotencyService,
                                       MediaIntakeService mediaIntakeService,
                                       JobEnqueuer jobEnqueuer,
                                       TransactionTemplate txTemplate,
                                       AssessmentRepository assessmentRepository,
                                       AssessmentGimbalRepository gimbalRepository,
                                       AssessmentMediaRepository mediaRepository,
                                       AssessmentAccessRepository accessRepository,
                                       PhotoVersions photoVersions,
                                       MediaCleanupEnqueuer mediaCleanupEnqueuer) {
        this.idempotencyService = idempotencyService;
        this.mediaIntakeService = mediaIntakeService;
        this.jobEnqueuer = jobEnqueuer;
        this.txTemplate = txTemplate;
        this.assessmentRepository = assessmentRepository;
        this.gimbalRepository = gimbalRepository;
        this.mediaRepository = mediaRepository;
        this.accessRepository = accessRepository;
        this.photoVersions = photoVersions;
        this.mediaCleanupEnqueuer = mediaCleanupEnqueuer;
    }

    public record Accepted(AssessmentTaskAccepted data, boolean replayed) {
    }

    private record TxOutcome(AssessmentTaskAccepted data, ErrorCode rejectionCode,
                             String rejectionMessage) {
        static TxOutcome accepted(AssessmentTaskAccepted data) {
            return new TxOutcome(data, null, null);
        }

        static TxOutcome rejected(ErrorCode code, String message) {
            return new TxOutcome(null, code, message);
        }
    }

    // ----------------------------------------------------------------- A01

    public Accepted acceptA01(PrincipalContext principal, String idempotencyKey, ParsedA01 parsed) {
        A01Metadata md = parsed.metadata();
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("photoVersion", md.photoVersion());
        fields.put("captureSessionId", md.captureSessionId());
        fields.put("consentEvidenceRef", md.consentEvidenceRef());
        String payloadHash = CanonicalObjectBuilder.forOperation(OPERATION_A01)
                .fields(fields)
                .imageParts(MediaIntakeService.partDigests(parsed.images()))
                .payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OPERATION_A01, idempotencyKey, payloadHash);
        switch (outcome) {
            case BeginOutcome.ReplaySucceeded replay ->
                    { return new Accepted(projectAccepted(replay.resultSummary()), true); }
            case BeginOutcome.ReplayRejected rejected ->
                    { throw IdempotencyService.replayedRejection(rejected); }
            case BeginOutcome.NewAttempt fresh -> {
                return acceptA01New(principal, fresh.handle(), parsed);
            }
        }
    }

    private Accepted acceptA01New(PrincipalContext principal, IdempotencyHandle handle,
                                  ParsedA01 parsed) {
        UUID gimbalId = principal.gimbalUuid();
        Map<String, MediaIntakeService.IngestedMedia> ingested;
        try {
            ingested = mediaIntakeService.ingest(principal, MediaPurpose.ASSESSMENT_SOURCE,
                    handle.requestId(), parsed.images());
        } catch (RuntimeException e) {
            mediaCleanupEnqueuer.enqueueOrphansFor(handle.requestId());
            throw e;
        }
        Map<String, String> mediaIds = mediaIds(ingested);

        TxOutcome outcome;
        try {
            outcome = txTemplate.execute(status -> {
            var gimbalOpt = gimbalRepository.lockById(gimbalId);
            if (gimbalOpt.isEmpty()) {
                return reject(handle, ErrorCode.RESOURCE_NOT_VISIBLE, "gimbal not visible");
            }
            AssessmentGimbalRepository.Pointer gimbal = gimbalOpt.get();

            var openExecution = accessRepository.findOpenByGimbal(gimbalId);
            if (openExecution.isPresent()) {
                ErrorCode code = "stopped".equals(openExecution.get().status())
                        ? ErrorCode.STOP_NOT_CONFIRMED : ErrorCode.DEVICE_OCCUPIED;
                String message = code == ErrorCode.STOP_NOT_CONFIRMED
                        ? "gimbal execution stopped but not closed"
                        : "gimbal has an open care execution";
                return reject(handle, code, message);
            }

            UUID taskId = UUID.randomUUID();
            assessmentRepository.insertQueued(taskId, gimbalId,
                    photoVersions.initial(mediaIds), handle.requestId());
            for (String mediaId : mediaIds.values()) {
                int claimed = mediaRepository.claim(UUID.fromString(mediaId), taskId, 1,
                        handle.requestId());
                if (claimed != 1) {
                    throw new ApiException(ErrorCode.INTERNAL, "media ownership claim failed");
                }
            }
            gimbalRepository.setCurrentAssessment(gimbalId, taskId);
            jobEnqueuer.enqueue(JOB_TYPE, "assessment", taskId, 1L, analyzePayload(taskId, 1),
                    "assessment:" + taskId + ":1");
            idempotencyService.completeSuccess(handle, "skin_assessment", taskId,
                    summary(taskId, "1", "queued"));
            long newRevision = gimbal.currentAssessmentRevision() + 1;
            return TxOutcome.accepted(new AssessmentTaskAccepted(
                    taskId.toString(), "queued", "1", String.valueOf(newRevision)));
            });
        } catch (RuntimeException e) {
            mediaCleanupEnqueuer.enqueueOrphansFor(handle.requestId());
            throw e;
        }

        return finish(outcome, handle.requestId());
    }

    // ----------------------------------------------------------------- A02

    public Accepted acceptA02(PrincipalContext principal, String idempotencyKey, UUID taskId,
                              String photoVersion, ParsedA02 parsed) {
        A02Metadata md = parsed.metadata();
        Map<String, Object> pathParams = new LinkedHashMap<>();
        pathParams.put("taskId", taskId.toString());
        pathParams.put("photoVersion", photoVersion);
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("expectedPhotoVersion", md.expectedPhotoVersion());
        fields.put("replacedViews", new LinkedHashSet<>(md.replacedViews()).stream().sorted().toList());
        String payloadHash = CanonicalObjectBuilder.forOperation(OPERATION_A02)
                .pathParams(pathParams)
                .fields(fields)
                .imageParts(MediaIntakeService.partDigests(parsed.images()))
                .payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OPERATION_A02, idempotencyKey, payloadHash);
        switch (outcome) {
            case BeginOutcome.ReplaySucceeded replay ->
                    { return new Accepted(projectAccepted(replay.resultSummary()), true); }
            case BeginOutcome.ReplayRejected rejected ->
                    { throw IdempotencyService.replayedRejection(rejected); }
            case BeginOutcome.NewAttempt fresh -> {
                return acceptA02New(principal, fresh.handle(), taskId, photoVersion, parsed);
            }
        }
    }

    private Accepted acceptA02New(PrincipalContext principal, IdempotencyHandle handle, UUID taskId,
                                  String photoVersion, ParsedA02 parsed) {
        UUID gimbalId = principal.gimbalUuid();
        Map<String, MediaIntakeService.IngestedMedia> ingested;
        try {
            ingested = mediaIntakeService.ingest(principal, MediaPurpose.ASSESSMENT_SOURCE,
                    handle.requestId(), parsed.images());
        } catch (RuntimeException e) {
            mediaCleanupEnqueuer.enqueueOrphansFor(handle.requestId());
            throw e;
        }
        Map<String, String> newMediaIds = mediaIds(ingested);
        A02Metadata md = parsed.metadata();

        TxOutcome outcome;
        try {
            outcome = txTemplate.execute(status -> {
            var gimbalOpt = gimbalRepository.lockById(gimbalId);
            if (gimbalOpt.isEmpty()) {
                return reject(handle, ErrorCode.RESOURCE_NOT_VISIBLE, "gimbal not visible");
            }
            AssessmentGimbalRepository.Pointer gimbal = gimbalOpt.get();

            var rowOpt = assessmentRepository.findByIdForUpdate(taskId);
            if (rowOpt.isEmpty()) {
                return reject(handle, ErrorCode.RESOURCE_NOT_VISIBLE, "assessment not visible");
            }
            AssessmentRepository.AcceptanceRow row = rowOpt.get();
            if (!gimbalId.equals(row.gimbalId())) {
                return reject(handle, ErrorCode.RESOURCE_NOT_VISIBLE, "assessment not visible");
            }
            if (!taskId.equals(gimbal.currentAssessmentId())) {
                return reject(handle, ErrorCode.TASK_REPLACED,
                        "assessment is no longer the gimbal current task");
            }
            if (!"needs_retake".equals(row.status())) {
                return reject(handle, ErrorCode.PHOTO_VERSION_CONFLICT,
                        "retake is only allowed while the task requires a retake");
            }
            Long current = row.currentPhotoVersion();
            Long pathVersion = parseLong(photoVersion);
            Long expected = parseLong(md.expectedPhotoVersion());
            if (pathVersion == null || expected == null
                    || !expected.equals(current) || pathVersion != current + 1) {
                return reject(handle, ErrorCode.PHOTO_VERSION_CONFLICT,
                        "photo version does not follow the current version");
            }
            long newVersion = current + 1;
            long newRevision = row.processingRevision() + 1;

            Map<String, String> merged = new LinkedHashMap<>(
                    photoVersions.imagesAtVersion(row.photoVersions(), current));
            for (String view : newMediaIds.keySet()) {
                merged.put(view, newMediaIds.get(view));
            }
            // 防御不变量：PhotoVersions.append 会静默丢弃缺失视角，合并清单必须
            // 恰好覆盖 front/left/right，否则拒绝追加（事务内抛 → 整体回滚）。
            if (!merged.keySet().equals(Set.of("front", "left", "right"))
                    || merged.values().stream().anyMatch(Objects::isNull)) {
                throw new ApiException(ErrorCode.INTERNAL,
                        "prior photo_versions view set is incomplete; refusing to append a"
                                + " partial version");
            }
            String newPhotoVersions = photoVersions.append(row.photoVersions(), newVersion, merged);
            int updated = assessmentRepository.updateRetake(taskId, newPhotoVersions, newVersion,
                    newRevision);
            if (updated != 1) {
                throw new ApiException(ErrorCode.INTERNAL, "retake update failed");
            }
            for (String mediaId : newMediaIds.values()) {
                int claimed = mediaRepository.claim(UUID.fromString(mediaId), taskId, newVersion,
                        handle.requestId());
                if (claimed != 1) {
                    throw new ApiException(ErrorCode.INTERNAL, "media ownership claim failed");
                }
            }
            jobEnqueuer.enqueue(JOB_TYPE, "assessment", taskId, newRevision,
                    analyzePayload(taskId, newRevision),
                    "assessment:" + taskId + ":" + newRevision);
            idempotencyService.completeSuccess(handle, "skin_assessment", taskId,
                    summary(taskId, String.valueOf(newVersion), "queued"));
            return TxOutcome.accepted(new AssessmentTaskAccepted(
                    taskId.toString(), "queued", String.valueOf(newVersion),
                    String.valueOf(gimbal.currentAssessmentRevision())));
            });
        } catch (RuntimeException e) {
            mediaCleanupEnqueuer.enqueueOrphansFor(handle.requestId());
            throw e;
        }

        return finish(outcome, handle.requestId());
    }

    // ------------------------------------------------------------- helpers

    private Accepted finish(TxOutcome outcome, UUID t13RequestId) {
        if (outcome.rejectionCode() != null) {
            // 确定性拒绝已提交：未接纳图片入队 media.cleanup（尽力而为，绝不上抛）
            mediaCleanupEnqueuer.enqueueOrphansFor(t13RequestId);
            throw new ApiException(outcome.rejectionCode(), outcome.rejectionMessage());
        }
        return new Accepted(outcome.data(), false);
    }

    /** 事务内确定性拒绝：写 T13 rejected 后返回拒绝结果（异常在提交后抛）。 */
    private TxOutcome reject(IdempotencyHandle handle, ErrorCode code, String message) {
        idempotencyService.completeRejected(handle, code, code.defaultStatus().value(),
                message, false, null);
        return TxOutcome.rejected(code, message);
    }

    private static Map<String, String> mediaIds(
            Map<String, MediaIntakeService.IngestedMedia> ingested) {
        Map<String, String> out = new LinkedHashMap<>();
        ingested.forEach((part, media) -> out.put(part, media.media().id().toString()));
        return out;
    }

    private static Map<String, Object> analyzePayload(UUID taskId, long processingRevision) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schema_version", 1);
        payload.put("assessment_id", taskId.toString());
        payload.put("processing_revision", String.valueOf(processingRevision));
        return payload;
    }

    private static Map<String, Object> summary(UUID taskId, String photoVersion, String status) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("schema_version", 1);
        summary.put("task_id", taskId.toString());
        summary.put("photo_version", photoVersion);
        summary.put("status", status);
        return summary;
    }

    /** 从 T13 存储摘要重建受理响应（不重做写入、不切指针）。 */
    private static AssessmentTaskAccepted projectAccepted(JsonNode summary) {
        return new AssessmentTaskAccepted(
                summary.path("task_id").asText(null),
                summary.path("status").asText("queued"),
                summary.path("photo_version").asText(null),
                null);
    }

    private static Long parseLong(String value) {
        if (value == null) {
            return null;
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException e) {
            return null;
        }
    }
}

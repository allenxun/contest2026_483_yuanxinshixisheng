package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.face.FaceServiceException;
import cn.yuanxin.mvp.web.idempotency.BeginOutcome;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import cn.yuanxin.mvp.web.idempotency.IdempotencyHandle;
import cn.yuanxin.mvp.web.idempotency.IdempotencyService;
import cn.yuanxin.mvp.web.idempotency.Jcs;
import cn.yuanxin.mvp.web.media.MediaIntakeService;
import cn.yuanxin.mvp.web.media.MediaIntakeService.IngestedMedia;
import cn.yuanxin.mvp.web.media.MediaPurpose;
import cn.yuanxin.mvp.web.media.MediaService;
import cn.yuanxin.mvp.web.web.CursorCodec;
import cn.yuanxin.mvp.web.web.CursorException;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.ListData;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.IOException;
import java.io.InputStream;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * M1 成员查看授权业务（M1-A01/A02/A03）。
 *
 * <p>永久授权：授权行不自动过期；撤销是 active→revoked 的标志位转移
 * （保留行，绝不删除），撤销后原 T13 重放必须 403 GRANT_REVOKED，重新授权
 * 需要新的人脸核验与新行/新 grantId。</p>
 *
 * <p>架构红线：只做有限次单表 SELECT/UPDATE（无 JOIN、无关联子查询）；
 * UPDATE 一律字段级；不创建/修改 members（只按
 * identity_namespace+face_subject_ref 只读定位）。</p>
 */
@Service
public class MemberAccessGrantService {

    private static final Logger log = LoggerFactory.getLogger(MemberAccessGrantService.class);

    public static final String OP_CREATE = "m1-a01-create-member-access-grant";
    public static final String OP_REVOKE = "m1-a03-revoke-member-access-grant";
    public static final String RESOURCE_TYPE = "member_access_grant";

    /** 无可靠匹配/身份歧义/越出候选范围：统一、不泄露存在性的 403 message。 */
    static final String FACE_NOT_VERIFIED_MESSAGE =
            "identity could not be confirmed and no linkable profile is available";
    /** 可见性失败（不存在/他人）：统一、不可区分的 404 message。 */
    static final String NOT_VISIBLE_MESSAGE = "grant not visible";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate txTemplate;
    private final IdempotencyService idempotencyService;
    private final MediaIntakeService mediaIntakeService;
    private final MediaService mediaService;
    private final FaceProvider faceProvider;
    private final FaceIdentityResolver faceIdentityResolver;
    private final CursorCodec cursorCodec;

    public MemberAccessGrantService(JdbcTemplate jdbc, TransactionTemplate txTemplate,
                                    IdempotencyService idempotencyService,
                                    MediaIntakeService mediaIntakeService, MediaService mediaService,
                                    FaceProvider faceProvider, FaceIdentityResolver faceIdentityResolver,
                                    CursorCodec cursorCodec) {
        this.jdbc = jdbc;
        this.txTemplate = txTemplate;
        this.idempotencyService = idempotencyService;
        this.mediaIntakeService = mediaIntakeService;
        this.mediaService = mediaService;
        this.faceProvider = faceProvider;
        this.faceIdentityResolver = faceIdentityResolver;
        this.cursorCodec = cursorCodec;
    }

    // ---------------- DTO / row shapes ----------------

    /** 控制器校验后的 A01 metadata（字段已在控制器侧做长度/时间/枚举校验）。 */
    public record CreateMetadata(String captureId, String capturedAt, String clientContinuityId,
                                 String purpose, String captureProofRef, String consentEvidenceRef) {
    }

    /** A01 结果：created=true → 201，replayed=true → meta.replayed。 */
    public record CreateOutcome(UUID grantId, UUID memberId, Instant grantedAt,
                                boolean created, boolean replayed) {
    }

    private record GrantRow(UUID id, UUID accountId, UUID memberId, String status, Instant grantedAt) {
    }

    private record GrantListRow(UUID id, UUID memberId, Instant grantedAt, Instant createdAt) {
    }

    // ---------------- M1-A01 ----------------

    public CreateOutcome createGrant(PrincipalContext principal, String idempotencyKey,
                                     CreateMetadata metadata, byte[] faceBytes) {
        requireApp(principal);

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("captureId", metadata.captureId());
        fields.put("capturedAt", metadata.capturedAt());
        fields.put("clientContinuityId", metadata.clientContinuityId());
        fields.put("purpose", metadata.purpose());
        fields.put("captureProofRef", metadata.captureProofRef());
        fields.put("consentEvidenceRef", metadata.consentEvidenceRef());
        fields.put("installationId", principal.installationId());
        fields.put("accountUuid", principal.accountUuid().toString());
        String payloadHash = CanonicalObjectBuilder.forOperation(OP_CREATE)
                .fields(fields)
                .imageParts(MediaIntakeService.partDigests(Map.of("face", faceBytes)))
                .payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OP_CREATE, idempotencyKey, payloadHash);
        return switch (outcome) {
            case BeginOutcome.ReplaySucceeded replay -> projectCreateReplay(principal, replay);
            case BeginOutcome.ReplayRejected rejected ->
                    throw IdempotencyService.replayedRejection(rejected);
            case BeginOutcome.NewAttempt fresh -> createFresh(principal, fresh.handle(), metadata, faceBytes);
        };
    }

    /** T13 重放：只定位原 grant 行，按当前状态投影（已撤销 → 403 GRANT_REVOKED）。 */
    private CreateOutcome projectCreateReplay(PrincipalContext principal,
                                              BeginOutcome.ReplaySucceeded replay) {
        if (!RESOURCE_TYPE.equals(replay.resourceType()) || replay.resourceId() == null) {
            throw new ApiException(ErrorCode.INTERNAL, "unexpected replay resource");
        }
        GrantRow row = loadGrant(replay.resourceId());
        if (row == null || !principal.accountUuid().equals(row.accountId())) {
            throw notVisible();
        }
        if (!"active".equals(row.status())) {
            // 已撤销的关系绝不复活。
            throw new ApiException(ErrorCode.GRANT_REVOKED,
                    "the member access grant was revoked; a new face verification is required");
        }
        return new CreateOutcome(row.id(), row.memberId(), row.grantedAt(), false, true);
    }

    private CreateOutcome createFresh(PrincipalContext principal, IdempotencyHandle handle,
                                      CreateMetadata metadata, byte[] faceBytes) {
        // 落 T11（pending→available）；存储失败由 MediaIntakeService 转 503，绝不继续核验。
        Map<String, IngestedMedia> ingested = mediaIntakeService.ingest(principal,
                MediaPurpose.GRANT_FACE, handle.requestId(), Map.of("face", faceBytes));
        IngestedMedia face = ingested.get("face");
        if (face == null) {
            throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE, "face image intake failed");
        }

        // 读回已存储对象，读写失败不得当作核验成功（fail closed）。
        byte[] stored = readStored(face);
        FaceClassification classification = classify(stored);

        switch (classification) {
            case QUALITY_REJECTED -> reject(handle, ErrorCode.FACE_QUALITY_REJECTED,
                    ErrorCode.FACE_QUALITY_REJECTED.defaultStatus().value(),
                    "face image rejected by quality checks");
            case DEPENDENCY_FAILED -> throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "face verification dependency unavailable");
            case MATCHED -> {
                // 继续
            }
            case RELIABLE_NEW, UNCERTAIN -> reject(handle, ErrorCode.FACE_NOT_VERIFIED, 403,
                    FACE_NOT_VERIFIED_MESSAGE);
        }

        Optional<ResolvedFaceIdentity> identity;
        try {
            identity = faceIdentityResolver.resolve(stored, classification);
        } catch (FaceServiceException dependencyFailure) {
            // resolve 内部会做第二次 1:N 搜索（FaceIdentityPort 契约：依赖故障由调用方映射）。
            // 与第一次搜索（上方 classify 的 DEPENDENCY_FAILED 分支）逐字一致的处置：
            // 503 DEPENDENCY_UNAVAILABLE、可重试；绝不降级为 403（那会把"服务不可用"谎报成
            // "人脸未通过"），也绝不放行到 500。异常消息/日志不含 namespace/subjectRef/图片/token。
            throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "face verification dependency unavailable");
        }
        if (identity.isEmpty()) {
            reject(handle, ErrorCode.FACE_NOT_VERIFIED, 403, FACE_NOT_VERIFIED_MESSAGE);
        }
        ResolvedFaceIdentity resolved = identity.get();

        // 只读 members（不建档）；库中无可靠成员与"未匹配上"给同一 403，避免存在性泄漏。
        UUID memberId = findActiveMember(resolved.identityNamespace(), resolved.faceSubjectRef());
        if (memberId == null) {
            reject(handle, ErrorCode.FACE_NOT_VERIFIED, 403, FACE_NOT_VERIFIED_MESSAGE);
        }

        // 外部存储/人脸调用已完成，进入短业务事务。
        try {
            return txTemplate.execute(status -> writeGrant(handle, principal, memberId, face,
                    classification, resolved, metadata));
        } catch (DuplicateKeyException race) {
            // 并发插入撞 uq_grant_active：另一事务已建立 active 行 → 复用既有行，200。
            log.info("member access grant insert raced uq_grant_active; reusing existing active grant");
            return txTemplate.execute(status -> {
                GrantRow existing = loadActiveGrant(principal.accountUuid(), memberId);
                if (existing == null) {
                    throw new ApiException(ErrorCode.INTERNAL,
                            "grant insert raced but no active grant is visible");
                }
                updateMediaOwnership(face, existing.memberId());
                idempotencyService.completeSuccess(handle, RESOURCE_TYPE, existing.id(),
                        successSummary(existing));
                return new CreateOutcome(existing.id(), existing.memberId(), existing.grantedAt(),
                        false, false);
            });
        }
    }

    private CreateOutcome writeGrant(IdempotencyHandle handle, PrincipalContext principal,
                                     UUID memberId, IngestedMedia face,
                                     FaceClassification classification, ResolvedFaceIdentity resolved,
                                     CreateMetadata metadata) {
        GrantRow existing = loadActiveGrant(principal.accountUuid(), memberId);
        if (existing != null) {
            updateMediaOwnership(face, existing.memberId());
            idempotencyService.completeSuccess(handle, RESOURCE_TYPE, existing.id(),
                    successSummary(existing));
            return new CreateOutcome(existing.id(), existing.memberId(), existing.grantedAt(),
                    false, false);
        }
        UUID grantId = UUID.randomUUID();
        jdbc.update("INSERT INTO member_access_grants (id, account_id, member_id, status,"
                        + " member_summary, verification_summary, source_request_id)"
                        + " VALUES (?, ?, ?, 'active', '{}'::jsonb, ?::jsonb, ?)",
                grantId, principal.accountUuid(), memberId,
                verificationSummary(classification, resolved, face, metadata), handle.requestId());
        updateMediaOwnership(face, memberId);
        GrantRow created = loadGrant(grantId);
        if (created == null) {
            throw new ApiException(ErrorCode.INTERNAL, "grant row missing after insert");
        }
        idempotencyService.completeSuccess(handle, RESOURCE_TYPE, grantId, successSummary(created));
        return new CreateOutcome(created.id(), created.memberId(), created.grantedAt(), true, false);
    }

    /** 字段级 T11 归属：仅补 member_id（request_id 在 ingest 已写）。 */
    private void updateMediaOwnership(IngestedMedia face, UUID memberId) {
        jdbc.update("UPDATE media_objects SET member_id = ?, updated_at = now() WHERE id = ?",
                memberId, face.media().id());
    }

    private Map<String, Object> successSummary(GrantRow row) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("grantId", row.id().toString());
        summary.put("memberId", row.memberId().toString());
        summary.put("grantedAt", EnvelopeSupport.rfc3339(row.grantedAt()));
        return summary;
    }

    /**
     * verification_summary（仅内部，绝不投影到响应）：核验分类、证据图片
     * mediaId、consentEvidenceRef、算法/提供方引用；JSONB 必须带 schema_version。
     */
    private String verificationSummary(FaceClassification classification,
                                       ResolvedFaceIdentity resolved, IngestedMedia face,
                                       CreateMetadata metadata) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("schema_version", 1);
        summary.put("classification", classification.name());
        summary.put("evidence_media_id", face.media().id().toString());
        summary.put("consent_evidence_ref", metadata.consentEvidenceRef());
        summary.put("provider", "face-provider-port");
        summary.put("identity_namespace", resolved.identityNamespace());
        return Jcs.canonicalize(Jcs.toNode(summary));
    }

    private byte[] readStored(IngestedMedia face) {
        InputStream in = mediaService.openContent(face.media());
        if (in == null) {
            throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "stored face image is unavailable");
        }
        try (in) {
            return in.readAllBytes();
        } catch (IOException e) {
            throw new ApiException(ErrorCode.DEPENDENCY_TIMEOUT, "stored face image read failed");
        }
    }

    private FaceClassification classify(byte[] content) {
        try {
            FaceClassification classification = faceProvider.classify("grant", content);
            return classification == null ? FaceClassification.DEPENDENCY_FAILED : classification;
        } catch (RuntimeException e) {
            // 人脸依赖异常绝不按通过处理。
            log.warn("face provider failure during M1-A01 classification");
            throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "face verification dependency unavailable");
        }
    }

    /** 确定性拒绝：写 T13 rejected（同键重试重放原拒绝），再抛业务错误。 */
    private void reject(IdempotencyHandle handle, ErrorCode code, int httpStatus, String message) {
        txTemplate.execute(status -> {
            idempotencyService.completeRejected(handle, code, httpStatus, message, false, null);
            return null;
        });
        throw new ApiException(code, httpStatus, false, message, null, Map.of());
    }

    private UUID findActiveMember(String identityNamespace, String faceSubjectRef) {
        List<UUID> rows = jdbc.query("SELECT id FROM members"
                        + " WHERE identity_namespace = ? AND face_subject_ref = ? AND status = 'active'",
                (rs, i) -> rs.getObject("id", UUID.class), identityNamespace, faceSubjectRef);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private GrantRow loadGrant(UUID grantId) {
        List<GrantRow> rows = jdbc.query("SELECT id, account_id, member_id, status, granted_at"
                        + " FROM member_access_grants WHERE id = ?",
                (rs, i) -> new GrantRow(rs.getObject("id", UUID.class),
                        rs.getObject("account_id", UUID.class),
                        rs.getObject("member_id", UUID.class),
                        rs.getString("status"), rs.getTimestamp("granted_at").toInstant()),
                grantId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private GrantRow loadActiveGrant(UUID accountId, UUID memberId) {
        List<GrantRow> rows = jdbc.query("SELECT id, account_id, member_id, status, granted_at"
                        + " FROM member_access_grants"
                        + " WHERE account_id = ? AND member_id = ? AND status = 'active'",
                (rs, i) -> new GrantRow(rs.getObject("id", UUID.class),
                        rs.getObject("account_id", UUID.class),
                        rs.getObject("member_id", UUID.class),
                        rs.getString("status"), rs.getTimestamp("granted_at").toInstant()),
                accountId, memberId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    // ---------------- M1-A02 ----------------

    public ListData<MemberAccessGrantListItem> listGrants(PrincipalContext principal, Integer limit,
                                                          String cursor) {
        requireApp(principal);
        int pageSize = cursorCodec.normalizeLimit(limit);
        String filterDigest = principal.accountUuid().toString();

        Instant cursorCreatedAt = null;
        UUID cursorId = null;
        if (cursor != null && !cursor.isBlank()) {
            CursorCodec.Cursor decoded = cursorCodec.decode(cursor);
            if (!filterDigest.equals(decoded.filterDigest())) {
                throw new CursorException("cursor does not belong to the current filter");
            }
            try {
                cursorCreatedAt = Instant.parse(decoded.sortValue());
                cursorId = UUID.fromString(decoded.id());
            } catch (RuntimeException e) {
                throw new CursorException("cursor values are invalid");
            }
        }

        List<GrantListRow> rows = new ArrayList<>();
        int fetch = pageSize + 1;
        if (cursorCreatedAt == null) {
            rows.addAll(jdbc.query("SELECT id, member_id, granted_at, created_at"
                            + " FROM member_access_grants"
                            + " WHERE account_id = ? AND status = 'active'"
                            + " ORDER BY created_at DESC, id DESC LIMIT ?",
                    (rs, i) -> mapListRow(rs), principal.accountUuid(), fetch));
        } else {
            rows.addAll(jdbc.query("SELECT id, member_id, granted_at, created_at"
                            + " FROM member_access_grants"
                            + " WHERE account_id = ? AND status = 'active'"
                            + " AND (created_at, id) < (?, ?)"
                            + " ORDER BY created_at DESC, id DESC LIMIT ?",
                    (rs, i) -> mapListRow(rs), principal.accountUuid(),
                    Timestamp.from(cursorCreatedAt), cursorId, fetch));
        }

        String nextCursor = null;
        if (rows.size() > pageSize) {
            GrantListRow last = rows.get(pageSize - 1);
            nextCursor = cursorCodec.encode(last.createdAt().toString(), last.id().toString(),
                    filterDigest);
            rows = rows.subList(0, pageSize);
        }
        List<MemberAccessGrantListItem> items = rows.stream()
                .map(r -> new MemberAccessGrantListItem(r.id().toString(), r.memberId().toString(),
                        EnvelopeSupport.rfc3339(r.grantedAt())))
                .toList();
        return new ListData<>(items, nextCursor);
    }

    private static GrantListRow mapListRow(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new GrantListRow(rs.getObject("id", UUID.class),
                rs.getObject("member_id", UUID.class),
                rs.getTimestamp("granted_at").toInstant(),
                rs.getTimestamp("created_at").toInstant());
    }

    // ---------------- M1-A03 ----------------

    public void revokeGrant(PrincipalContext principal, UUID grantId, String idempotencyKey) {
        requireApp(principal);

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("accountUuid", principal.accountUuid().toString());
        fields.put("installationId", principal.installationId());
        String payloadHash = CanonicalObjectBuilder.forOperation(OP_REVOKE)
                .pathParams(Map.of("grantId", grantId.toString()))
                .fields(fields)
                .payloadHash();

        BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                principal.t13PrincipalId(), OP_REVOKE, idempotencyKey, payloadHash);
        switch (outcome) {
            case BeginOutcome.ReplaySucceeded ignored -> {
                // 重复撤销（同键重放）→ 204，不再写。
            }
            case BeginOutcome.ReplayRejected rejected ->
                    throw IdempotencyService.replayedRejection(rejected);
            case BeginOutcome.NewAttempt fresh -> revokeFresh(principal, grantId, fresh.handle());
        }
    }

    private void revokeFresh(PrincipalContext principal, UUID grantId, IdempotencyHandle handle) {
        Boolean visible = txTemplate.execute(status -> {
            List<GrantRow> rows = jdbc.query("SELECT id, account_id, member_id, status, granted_at"
                            + " FROM member_access_grants WHERE id = ? FOR UPDATE",
                    (rs, i) -> new GrantRow(rs.getObject("id", UUID.class),
                            rs.getObject("account_id", UUID.class),
                            rs.getObject("member_id", UUID.class),
                            rs.getString("status"), rs.getTimestamp("granted_at").toInstant()),
                    grantId);
            if (rows.isEmpty() || !principal.accountUuid().equals(rows.get(0).accountId())) {
                idempotencyService.completeRejected(handle, ErrorCode.RESOURCE_NOT_VISIBLE,
                        ErrorCode.RESOURCE_NOT_VISIBLE.defaultStatus().value(),
                        NOT_VISIBLE_MESSAGE, false, null);
                return Boolean.FALSE;
            }
            if ("active".equals(rows.get(0).status())) {
                // 只写 status/revoked_at/updated_at；不删除行、不触碰后续新 grant。
                jdbc.update("UPDATE member_access_grants"
                                + " SET status = 'revoked', revoked_at = now(), updated_at = now()"
                                + " WHERE id = ? AND status = 'active'",
                        grantId);
            }
            idempotencyService.completeSuccess(handle, RESOURCE_TYPE, grantId,
                    Map.of("grantId", grantId.toString(), "status", "revoked"));
            return Boolean.TRUE;
        });
        if (!Boolean.TRUE.equals(visible)) {
            throw notVisible();
        }
    }

    // ---------------- shared ----------------

    private static void requireApp(PrincipalContext principal) {
        if (principal.principalType() != PrincipalType.APP) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "this endpoint is only available to app account sessions");
        }
    }

    private static ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, NOT_VISIBLE_MESSAGE);
    }

    /** A02 列表元素（不得包含 memberSummary：形状未冻结，直接省略以免漂移）。 */
    public record MemberAccessGrantListItem(String grantId, String memberId, String grantedAt) {
    }
}

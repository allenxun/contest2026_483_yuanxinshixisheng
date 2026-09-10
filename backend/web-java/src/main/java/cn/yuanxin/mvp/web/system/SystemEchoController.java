package cn.yuanxin.mvp.web.system;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.BeginOutcome;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import cn.yuanxin.mvp.web.idempotency.IdempotencyHandle;
import cn.yuanxin.mvp.web.idempotency.IdempotencyService;
import cn.yuanxin.mvp.web.jobs.JobEnqueuer;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import cn.yuanxin.mvp.web.web.SuccessEnvelope;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 基础系统端点（跨语言 E2E 验收桥，x-foundation / x-implementation:
 * foundation-system；不计入 27）：
 *
 * <ul>
 *   <li>POST /api/v1/system/echo-jobs：已认证主体（APP 或 GIMBAL）提交回声
 *       任务 → 经 JobEnqueuer 入队 system.echo。<b>创建者身份</b>写入 A 属主列
 *       （RV-5 裁定）：APP → owner_type='app_account', owner_id=accountUuid；
 *       GIMBAL → owner_type='gimbal', owner_id=gimbalUuid。installation 只属 T13
 *       作用域，不进 owner_id（同账号不同安装可读自己账号的任务）。payload 带
 *       schema_version=1、bigint 字符串。Idempotency-Key 可选：提供时走 T13
 *       （operation=system.echo.create），重放同 jobId + meta.replayed=true。</li>
 *   <li>GET /api/v1/system/echo-jobs/{jobId}：<b>仅创建者本人</b>可读自己的
 *       system.echo 任务。不存在 / job_type≠system.echo / 非创建者 → 同一
 *       404 RESOURCE_NOT_VISIBLE（不泄露存在性/归属/类型；沿用 Bearer 认证，
 *       未认证先 401）。投影 async_jobs 当前状态（attemptCount/leaseRevision 为
 *       bigint 字符串）。lastError 是<b>有界安全投影</b>：仅 {reason 枚举,
 *       retryable bool}，内部诊断列（raw code/message/stack）绝不外泄
 *       （见 {@link #projectError}）。</li>
 * </ul>
 *
 * <p>本端点是 B/C/D 接线 T13 + JobEnqueuer + PrincipalContext 的参照实现。</p>
 */
@RestController
@RequestMapping("/api/v1/system/echo-jobs")
public class SystemEchoController {

    /** 契约固定 operation（canonicalObject 首键）。 */
    public static final String OPERATION = "system.echo.create";
    public static final String JOB_TYPE = "system.echo";

    private final JobEnqueuer jobEnqueuer;
    private final IdempotencyService idempotencyService;
    private final TransactionTemplate txTemplate;
    private final JdbcTemplate jdbc;
    private final EnvelopeSupport envelopes;

    public SystemEchoController(JobEnqueuer jobEnqueuer, IdempotencyService idempotencyService,
                                TransactionTemplate txTemplate, JdbcTemplate jdbc,
                                EnvelopeSupport envelopes) {
        this.jobEnqueuer = jobEnqueuer;
        this.idempotencyService = idempotencyService;
        this.txTemplate = txTemplate;
        this.jdbc = jdbc;
        this.envelopes = envelopes;
    }

    public record EchoJobRequestBody(
            @NotBlank @Size(max = 512) String message,
            @Size(max = 32) List<@Pattern(regexp = "^(0|[1-9][0-9]*)$",
                    message = "numbersAsStrings items must be unsigned decimal bigint strings") String>
                    numbersAsStrings,
            @Pattern(regexp = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    + "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
                    message = "jobId must be a UUID string") String jobId) {
    }

    public record EchoJobAcceptedData(String jobId, String dedupKey, String status) {
    }

    public record EchoJobViewData(String jobId, String status, String attemptCount,
                                  String leaseRevision, String finishedAt,
                                  EchoJobLastError lastError) {
    }

    /**
     * 外部有界失败投影（契约 components.schemas.EchoJobLastError）：
     * <b>恰两个字段</b> reason（白名单归一 enum）+ retryable（bool）。内部诊断
     * （raw code / message / stack / retry_after_seconds）绝不投影；未知/缺失/
     * 非对象/非 JSON 一律 reason="internal"。有界投影而非截断（无自由文本字段，
     * 4058 字符 message 不可能出现）。
     */
    public record EchoJobLastError(String reason, boolean retryable) {
    }

    private static final ObjectMapper LAST_ERROR_MAPPER = new ObjectMapper();
    private static final String REASON_INTERNAL = "internal";
    private static final String REASON_UNSUPPORTED_CONTRACT = "unsupported_contract";
    private static final String REASON_RETRY_LIMIT_EXCEEDED = "retry_limit_exceeded";
    /** 契约保留值：system.echo 当前无 JobFailed code（见 handlers/system_echo.py）。 */
    private static final String REASON_HANDLER_FAILED = "handler_failed";

    /** GET 行装载：含归属列（仅内部 creator 判定，绝不投影给客户端）。 */
    private record LoadedEchoJob(String jobType, String ownerType, UUID ownerId, String status,
                                 EchoJobViewData view) {
    }

    /**
     * 创建者归属类型（RV-5 裁定）：APP 账号任务用 {@code app_account}，云台任务用
     * {@code gimbal}。落到 A 属主列 async_jobs.owner_type。
     */
    private static String creatorOwnerType(PrincipalContext principal) {
        return principal.principalType() == PrincipalType.APP ? "app_account" : "gimbal";
    }

    /** 创建者归属 id：APP=accountUuid（installation 不进 owner_id），GIMBAL=gimbalUuid。 */
    private static UUID creatorOwnerId(PrincipalContext principal) {
        return principal.principalType() == PrincipalType.APP
                ? principal.accountUuid() : principal.gimbalUuid();
    }

    /**
     * 行是否属于当前创建者且是 echo 类型。三要素全部来自持久化行 + 认证主体，
     * 不信任任何请求输入；不匹配由调用方统一转 404。
     */
    private static boolean creatorOwns(LoadedEchoJob row, PrincipalContext principal) {
        UUID ownerId = creatorOwnerId(principal);
        return JOB_TYPE.equals(row.jobType())
                && creatorOwnerType(principal).equals(row.ownerType())
                && ownerId != null && ownerId.equals(row.ownerId());
    }

    private static ApiException notVisible() {
        // 不存在 / 非 echo / 非创建者：完全相同的错误（不泄露存在性/归属/类型）
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, "job not visible");
    }

    @PostMapping
    public ResponseEntity<SuccessEnvelope> create(@Valid @RequestBody EchoJobRequestBody body,
                                                  @RequestHeader(value = "Idempotency-Key",
                                                          required = false)
                                                  @Size(max = 128) String idempotencyKey,
                                                  PrincipalContext principal,
                                                  HttpServletRequest request) {
        List<String> numbers = body.numbersAsStrings() == null ? List.of() : body.numbersAsStrings();
        String dedupKey = "system:echo:"
                + (body.jobId() != null ? body.jobId().toLowerCase(java.util.Locale.ROOT)
                        : UUID.randomUUID().toString());

        // canonical：message + numbersAsStrings（有序数组保持原序）+ jobId（缺省展开为 null）
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("message", body.message());
        fields.put("numbersAsStrings", numbers);
        fields.put("jobId", body.jobId() == null ? null : body.jobId().toLowerCase(java.util.Locale.ROOT));
        String payloadHash = CanonicalObjectBuilder.forOperation(OPERATION)
                .fields(fields)
                .payloadHash();

        IdempotencyHandle handle = null;
        if (idempotencyKey != null && !idempotencyKey.isBlank()) {
            BeginOutcome outcome = idempotencyService.begin(principal.t13PrincipalType(),
                    principal.t13PrincipalId(), OPERATION, idempotencyKey, payloadHash);
            switch (outcome) {
                case BeginOutcome.ReplaySucceeded replay -> {
                    request.setAttribute(EnvelopeSupport.ATTR_REPLAYED, Boolean.TRUE);
                    EchoJobAcceptedData data = projectReplay(replay, dedupKeyOf(replay), principal);
                    return ResponseEntity.ok(envelopes.ok(request, data, true));
                }
                case BeginOutcome.ReplayRejected rejected ->
                        throw IdempotencyService.replayedRejection(rejected);
                case BeginOutcome.NewAttempt fresh -> handle = fresh.handle();
            }
        }

        // 受理 + 入队 + T13 succeeded 同一事务（digest §4：提交即完成交接）
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schema_version", 1);
        payload.put("message", body.message());
        payload.put("numbers_as_strings", numbers);
        final UUID serverJobId = UUID.randomUUID();
        final IdempotencyHandle h = handle;
        final String ownerType = creatorOwnerType(principal);
        final UUID ownerId = creatorOwnerId(principal);
        JobEnqueuer.JobEnqueueResult result = txTemplate.execute(status -> {
            JobEnqueuer.JobEnqueueResult r = jobEnqueuer.enqueue(JOB_TYPE, ownerType,
                    ownerId, 0, payload, dedupKey);
            if (h != null) {
                idempotencyService.completeSuccess(h, "async_job", r.jobId(),
                        Map.of("jobId", r.jobId().toString(), "dedupKey", dedupKey));
            }
            return r;
        });
        return ResponseEntity.ok(envelopes.ok(request,
                new EchoJobAcceptedData(result.jobId().toString(), dedupKey, result.status())));
    }

    @GetMapping("/{jobId}")
    public SuccessEnvelope get(@PathVariable("jobId") UUID jobId, PrincipalContext principal,
                               HttpServletRequest request) {
        var rows = jdbc.query("SELECT id, job_type, owner_type, owner_id, status, attempt_count,"
                        + " lease_revision, finished_at, last_error::text AS last_error"
                        + " FROM async_jobs WHERE id = ?",
                (rs, i) -> new LoadedEchoJob(
                        rs.getString("job_type"), rs.getString("owner_type"),
                        rs.getObject("owner_id", UUID.class), rs.getString("status"),
                        new EchoJobViewData(
                                rs.getObject("id", UUID.class).toString(),
                                rs.getString("status"),
                                String.valueOf(rs.getLong("attempt_count")),
                                String.valueOf(rs.getLong("lease_revision")),
                                rs.getTimestamp("finished_at") == null ? null
                                        : EnvelopeSupport.rfc3339(
                                                rs.getTimestamp("finished_at").toInstant()),
                                projectError(rs.getString("last_error")))),
                jobId);
        if (rows.isEmpty() || !creatorOwns(rows.get(0), principal)) {
            throw notVisible();
        }
        return envelopes.ok(request, rows.get(0).view());
    }

    /**
     * 内部 last_error（JSONB 诊断列）→ 外部有界投影。任何解析失败、非对象、
     * 缺失 code、未知 code → reason=internal, retryable=false；绝不返回原始文本。
     * 已知安全 code 经白名单归一；raw code 串永不外泄。
     */
    static EchoJobLastError projectError(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        JsonNode node;
        try {
            node = LAST_ERROR_MAPPER.readTree(raw);
        } catch (Exception parseFailure) {
            return new EchoJobLastError(REASON_INTERNAL, false);
        }
        if (node == null || !node.isObject()) {
            return new EchoJobLastError(REASON_INTERNAL, false);
        }
        String code = node.path("code").asText(null);
        JsonNode retryableNode = node.path("retryable");
        boolean retryable = retryableNode.isBoolean() && retryableNode.booleanValue();
        return new EchoJobLastError(mapReason(code), retryable);
    }

    /** INTERNAL code → 外部 reason 白名单；未知/缺失 → internal。 */
    private static String mapReason(String code) {
        if (code == null) {
            return REASON_INTERNAL;
        }
        return switch (code) {
            case "UNSUPPORTED_CONTRACT" -> REASON_UNSUPPORTED_CONTRACT;
            case "RETRY_LIMIT_EXCEEDED" -> REASON_RETRY_LIMIT_EXCEEDED;
            default -> REASON_INTERNAL;
        };
    }

    private static String dedupKeyOf(BeginOutcome.ReplaySucceeded replay) {
        return replay.resultSummary().path("dedupKey").asText(null);
    }

    /**
     * succeeded 重放：只定位原资源，按当前 DB 状态投影（不重复入队）。T13 作用域
     * 已含 principal，故重放行按构造即同创建者；此处仍显式复核 creator 归属
     * （防御性，绝不因重放而跨主体暴露），不匹配统一 404。
     */
    private EchoJobAcceptedData projectReplay(BeginOutcome.ReplaySucceeded replay, String dedupKey,
                                              PrincipalContext principal) {
        if (!"async_job".equals(replay.resourceType()) || replay.resourceId() == null) {
            throw new ApiException(ErrorCode.INTERNAL, "unexpected replay resource");
        }
        var rows = jdbc.query("SELECT job_type, owner_type, owner_id, status"
                        + " FROM async_jobs WHERE id = ?",
                (rs, i) -> new LoadedEchoJob(
                        rs.getString("job_type"), rs.getString("owner_type"),
                        rs.getObject("owner_id", UUID.class), rs.getString("status"), null),
                replay.resourceId());
        if (rows.isEmpty() || !creatorOwns(rows.get(0), principal)) {
            throw notVisible();
        }
        return new EchoJobAcceptedData(replay.resourceId().toString(), dedupKey, rows.get(0).status());
    }
}

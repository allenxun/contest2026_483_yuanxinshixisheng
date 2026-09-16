package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.jobs.Uuid5;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.UUID;

/**
 * <b>Java → Worker 身份结果合同</b>的唯一权威定义（冻结；D 可直接照此消费，无需猜测未提交的实现）。
 *
 * <p><b>承载位置（总协调 2026-09-16 裁定后由 orchestrator 确定）</b>：T01 {@code members} 的现有列
 * {@code identity_namespace} / {@code face_subject_ref} / {@code identity_summary}(jsonb) /
 * {@code status} / {@code created_from_assessment_id}。<b>不需要任何公共迁移</b>——列
 * （{@code V1__create_tables.sql:76-92}）、部分唯一索引 {@code uq_members_identity}
 * （{@code :94-96}，两列均非空时唯一）与 schema CHECK（{@code :88-91}，要求
 * {@code identity_summary} 为空占位或含<b>数值型</b> {@code schema_version}）全部已存在。
 *
 * <p><b>Java 绝不写 T05 {@code skin_assessments.identity_result}</b>：该列是 Worker 独占列
 * （{@code AssessmentRepository.java:14,99}、{@code PhotoVersions.java:21} 逐字记载），
 * 且它是 M3-A03 {@code requiredViews} 投影的唯一权威通道（{@code FailureProjection.java:13,85}）。
 * 字段归属划分见 {@code backend/handoffs/B-identity-result-contract.md}。
 *
 * <p><b>跨语言稳定派生</b>：{@link #FIXED_NS} 与四个派生键与
 * {@code worker-python/src/mvp_worker/handlers/dshared/constants.py:9,21-45} <b>逐字一致</b>，
 * 权威来源是 {@code backend/contracts/decisions-notes.md:41-53}（"两侧硬编码，
 * 禁止各算各的输入差异"）。Java 侧复用 A 域既有的 {@link Uuid5}（RFC 4122 UUIDv5 / SHA-1，
 * 与 Python {@code uuid.uuid5} 字节一致），<b>不</b>另造实现。
 */
public final class IdentityResultContract {

    /** 合同版本。落库为 {@code identity_summary.schema_version}（DB CHECK 要求<b>数值型</b>）。 */
    public static final int SCHEMA_VERSION = 1;

    /** 与 Python {@code dshared/constants.py:9} 及 {@code decisions-notes.md:44} 逐字相同。 */
    public static final UUID FIXED_NS = Uuid5.FIXED_NS;

    // ---- 派生键前缀（与 Python constants.py:21-24 逐字一致）----
    private static final String CANDIDATE_PREFIX = "face-candidate";
    private static final String CORRELATION_PREFIX = "enroll-correlation";
    private static final String REQUEST_PREFIX = "enroll-request";

    // ---- identity_summary 的冻结字段名（改名即破坏合同）----
    public static final String F_SCHEMA_VERSION = "schema_version";
    public static final String F_ENROLLMENT = "enrollment";
    public static final String F_REFERENCE_MEDIA = "reference_media";
    public static final String F_DECISION = "decision";
    public static final String F_CORRELATION_ID = "correlation_id";
    public static final String F_PROVIDER_REQUEST_ID = "provider_request_id";
    public static final String F_PROVIDER_CONFIG_REVISION = "provider_config_revision";
    public static final String F_REGISTERED_AT = "registered_at";
    public static final String F_SOURCE_ASSESSMENT_ID = "source_assessment_id";
    public static final String F_PHOTO_VERSION = "photo_version";
    public static final String F_PROCESSING_REVISION = "processing_revision";
    public static final String F_PHASE = "phase";
    public static final String F_CANDIDATE_ENTITY_ID = "candidate_entity_id";
    public static final String F_POLICY_VERSION = "policy_version";
    public static final String F_MODEL_VERSION = "model_version";
    public static final String F_LIBRARY_REVISION = "library_revision";
    public static final String F_CLASSIFICATION = "classification";
    public static final String F_SEARCH_DECISION = "search_decision";
    public static final String F_MATCHED_SUBJECT_REF = "matched_subject_ref";

    /** 三视角固定枚举（与 Python {@code constants.py:18} 的 {@code REQUIRED_VIEWS_ALL} 一致）。 */
    public static final String VIEW_FRONT = "front";
    public static final String VIEW_LEFT = "left";
    public static final String VIEW_RIGHT = "right";

    /**
     * {@code decision.classification} 的取值域（<b>保守</b>）。
     *
     * <p><b>刻意没有 "reliable_new"</b>：1:N 搜索"没匹配"不构成"可靠新人"的证据
     * （{@code 后端详细设计-V1-MVP.md:657}「歧义不归档，未命中只成为新人候选」、
     * {@code :663}「自动新人判定阈值、活体条件未通过 PoC 则不得开启真实自动登记」）。
     * 因此本合同只在<b>已经</b>完成受控登记后记录结果，不承载"判定为新人"这一决定本身。
     */
    public static final String CLASSIFICATION_RELIABLE_NEW_CANDIDATE_ENROLLED = "reliable_new_candidate_enrolled";
    /** 搜索命中既有主体、复用既有成员行（未新建成员）。 */
    public static final String CLASSIFICATION_MATCHED_EXISTING = "matched_existing";

    /** ISO-8601、UTC、秒精度、以 {@code Z} 结尾（与 Python {@code identity_enroll.py:346-349} 一致）。 */
    private static final DateTimeFormatter REGISTERED_AT_FORMAT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'").withZone(ZoneOffset.UTC);

    private IdentityResultContract() {
    }

    // ---------------------------------------------------------------- 派生键

    /**
     * 确定性人脸主体引用（= {@code members.face_subject_ref} = D 既有 {@code candidate_entity_id}）。
     *
     * <p>与 Python {@code constants.py:27-28} 逐字一致：
     * {@code uuid5(FIXED_NS, "face-candidate:<namespace>:<assessmentId>")}。
     * <b>跨重试稳定</b>是"远端成功 + 本地失败"可对账的前提，因此<b>绝不</b>改用随机 UUID。
     */
    public static String candidateEntityId(String identityNamespace, UUID assessmentId) {
        requireText(identityNamespace, "identityNamespace");
        if (assessmentId == null) {
            throw new IllegalArgumentException("assessmentId must not be null");
        }
        return Uuid5.uuid5(FIXED_NS, CANDIDATE_PREFIX + ":" + identityNamespace + ":" + assessmentId).toString();
    }

    /** 与 Python {@code constants.py:31-32} 一致：{@code uuid5(FIXED_NS, "enroll-correlation:<ns>:<assessmentId>")}。 */
    public static String enrollCorrelationId(String identityNamespace, UUID assessmentId) {
        requireText(identityNamespace, "identityNamespace");
        if (assessmentId == null) {
            throw new IllegalArgumentException("assessmentId must not be null");
        }
        return Uuid5.uuid5(FIXED_NS, CORRELATION_PREFIX + ":" + identityNamespace + ":" + assessmentId).toString();
    }

    /** 与 Python {@code constants.py:44-45} 一致：{@code uuid5(FIXED_NS, "enroll-request:<correlationId>")}。 */
    public static String providerRequestId(String correlationId) {
        requireText(correlationId, "correlationId");
        return Uuid5.uuid5(FIXED_NS, REQUEST_PREFIX + ":" + correlationId).toString();
    }

    /**
     * identity.enroll 的 T12 {@code owner_id}（<b>namespace 级</b>）。
     *
     * <p>与 Python {@code constants.py:35-41} 一致，其 docstring 明写「用 namespace 级 owner
     * （而非 per-person）让 {@code uq_job_identity_enroll} 在整个 namespace 上串行」，
     * 依据 {@code 后端详细设计-V1-MVP.md:736}。
     *
     * <p><b>已知不一致（如实登记，orchestrator 不擅自修改 A 域文件）</b>：
     * {@code jobs/JobEnqueuer.java:127-129} 的 {@code identityNamespaceOwnerFor(ns, faceSubjectRef)}
     * 是 <b>per-subject</b> 派生，且 {@code contracts/decisions-notes.md:33} 也写 per-subject；
     * 但该方法全仓<b>调用方为 0</b>（死代码），实际生产路径用的是 Python 的 namespace 级值。
     * 若将来误用该 Java 方法，会让同一 namespace 并发多条未决登记、破坏
     * {@code uq_job_identity_enroll}（{@code V1:473-476}）的串行化意图。
     * 已作为协调项上报总协调与 A。
     */
    public static String namespaceOwnerId(String identityNamespace) {
        requireText(identityNamespace, "identityNamespace");
        return Uuid5.uuid5(FIXED_NS, "identity-namespace:" + identityNamespace).toString();
    }

    // ---------------------------------------------------------------- JSON 构造

    /**
     * 构造 {@code members.identity_summary} 的冻结 JSON（{@link #SCHEMA_VERSION}）。
     *
     * <p><b>必须保留 {@code reference_media} 且值为 media id 字符串</b>：D 的
     * {@code media_cleanup.py:71-78} 以 {@code CAST(identity_summary AS text) LIKE '%media_id%'}
     * 判断参考照是否仍被引用；若本形状缺失或改写这些 id，<b>参考照会被误删</b>。
     * 这是本合同最容易被忽视的跨包耦合，故在此逐字记载。
     *
     * <p>形状与 D 既有 {@code identity_enroll.py:331-358} 的 {@code _identity_summary()}
     * <b>向后兼容</b>（保留 {@code schema_version} / {@code enrollment} / {@code reference_media}
     * 三个顶层键与 {@code enrollment} 内既有六键），并<b>追加</b>围栏与审计字段
     * （{@code processing_revision}、{@code phase}、{@code candidate_entity_id}、
     * {@code policy_version}、{@code model_version}、{@code library_revision}）与 {@code decision} 段。
     */
    public static ObjectNode buildIdentitySummary(IdentityEnrollmentCommand command,
                                                 IdentityEnrollmentResult result) {
        if (command == null) {
            throw new IllegalArgumentException("command must not be null");
        }
        if (result == null) {
            throw new IllegalArgumentException("result must not be null");
        }
        JsonNodeFactory f = JsonNodeFactory.instance;
        ObjectNode root = f.objectNode();
        root.put(F_SCHEMA_VERSION, SCHEMA_VERSION);

        ObjectNode enrollment = root.putObject(F_ENROLLMENT);
        enrollment.put(F_CORRELATION_ID, command.correlationId());
        enrollment.put(F_PROVIDER_REQUEST_ID, command.providerRequestId());
        enrollment.put(F_PROVIDER_CONFIG_REVISION, command.providerConfigRevision());
        enrollment.put(F_REGISTERED_AT, formatRegisteredAt(result.registeredAt()));
        enrollment.put(F_SOURCE_ASSESSMENT_ID, command.assessmentId().toString());
        enrollment.put(F_PHOTO_VERSION, command.photoVersion());
        enrollment.put(F_PROCESSING_REVISION, command.processingRevision());
        enrollment.put(F_PHASE, result.phase().wireValue());
        enrollment.put(F_CANDIDATE_ENTITY_ID, result.faceSubjectRef());
        enrollment.put(F_POLICY_VERSION, command.policyVersion());
        enrollment.put(F_MODEL_VERSION, command.modelVersion());
        enrollment.put(F_LIBRARY_REVISION, command.libraryRevision());

        ObjectNode referenceMedia = root.putObject(F_REFERENCE_MEDIA);
        referenceMedia.put(VIEW_FRONT, command.referenceMediaFront());
        referenceMedia.put(VIEW_LEFT, command.referenceMediaLeft());
        referenceMedia.put(VIEW_RIGHT, command.referenceMediaRight());

        ObjectNode decision = root.putObject(F_DECISION);
        decision.put(F_CLASSIFICATION, result.classification());
        decision.put(F_SEARCH_DECISION, command.searchDecision());
        if (result.matchedExistingSubjectRef() == null) {
            decision.putNull(F_MATCHED_SUBJECT_REF);
        } else {
            decision.put(F_MATCHED_SUBJECT_REF, result.matchedExistingSubjectRef());
        }
        return root;
    }

    /** {@code registered_at} 的冻结格式：ISO-8601、UTC、秒精度、{@code Z} 结尾。 */
    public static String formatRegisteredAt(Instant registeredAt) {
        if (registeredAt == null) {
            throw new IllegalArgumentException("registeredAt must not be null");
        }
        return REGISTERED_AT_FORMAT.format(registeredAt);
    }

    private static void requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }
}

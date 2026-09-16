package cn.yuanxin.mvp.web.identity;

import java.time.Instant;
import java.util.UUID;

/**
 * 身份登记的<b>冻结输出</b>（Java→Worker 身份结果合同的一部分）。
 *
 * <p><b>可见性时点（合同核心，必须严格遵守）</b>：本结果只在<b>成员行已提交</b>之后返回。
 * 因此 {@code memberId} 与 {@code faceSubjectRef} 一旦出现在本结果中，就意味着
 * {@code members} 里已存在一行满足
 * {@code identity_namespace = ? AND face_subject_ref = ? AND status = 'active'}，
 * 即 {@code MemberAccessGrantService} 的只读定位（{@code :321-326}）与 D 的
 * {@code _SELECT_MEMBER_BY_REF}（{@code assessment_analyze.py:106-108}）<b>都能立刻查到</b>。
 * 绝不返回"远端已登记但本地未提交"的中间态——那种情况下必须抛异常让调用方重试对账，
 * 而不是产出一个查不到的 memberId。
 *
 * <p>{@code faceSubjectRef} 与 {@code memberId} 属<b>内部</b>身份引用：绝不投影到任何对外
 * HTTP 响应（{@code ResolvedFaceIdentity} 的既有纪律、{@code openapi.yaml:2343}
 * "绝不投影 failure_detail / identity_result 等内部诊断"），也绝不写入日志。
 *
 * @param memberId                 已提交的 T01 成员行主键（非 null）
 * @param identityNamespace          身份库命名空间
 * @param faceSubjectRef             确定性人脸主体引用（= {@code candidate_entity_id}）
 * @param phase                      终态相位，只能是 {@link IdentityEnrollmentPhase#ENROLLED}
 *                                   或 {@link IdentityEnrollmentPhase#ENROLLED_RECONCILED}
 * @param classification             {@link IdentityResultContract} 中定义的保守分类字面值
 * @param matchedExistingSubjectRef  仅当搜索命中<b>既有</b>主体（复用既有成员行、未新建）时非 null；
 *                                   新建登记时为 null
 * @param registeredAt               远端登记被确认的时刻（UTC 秒精度，落库格式见
 *                                   {@link IdentityResultContract#formatRegisteredAt}）
 * @param memberRowInserted          本次调用是否<b>真的</b>插入了新成员行；
 *                                   false 表示命中 {@code uq_members_identity} 冲突后回查到既有行
 *                                   （幂等重试的正常结果，不是错误）
 */
public record IdentityEnrollmentResult(
        UUID memberId,
        String identityNamespace,
        String faceSubjectRef,
        IdentityEnrollmentPhase phase,
        String classification,
        String matchedExistingSubjectRef,
        Instant registeredAt,
        boolean memberRowInserted) {

    public IdentityEnrollmentResult {
        if (memberId == null) {
            throw new IllegalArgumentException("memberId must not be null");
        }
        if (identityNamespace == null || identityNamespace.isBlank()) {
            throw new IllegalArgumentException("identityNamespace must not be blank");
        }
        if (faceSubjectRef == null || faceSubjectRef.isBlank()) {
            throw new IllegalArgumentException("faceSubjectRef must not be blank");
        }
        if (phase == null) {
            throw new IllegalArgumentException("phase must not be null");
        }
        if (!phase.isJavaTerminal()) {
            // 只允许两个 Java 终态；enroll_pending / enroll_started 属 T05 且由 Worker 写。
            throw new IllegalArgumentException("phase must be a Java terminal phase");
        }
        if (classification == null || classification.isBlank()) {
            throw new IllegalArgumentException("classification must not be blank");
        }
        if (registeredAt == null) {
            throw new IllegalArgumentException("registeredAt must not be null");
        }
    }
}

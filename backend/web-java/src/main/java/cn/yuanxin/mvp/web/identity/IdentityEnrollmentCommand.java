package cn.yuanxin.mvp.web.identity;

import java.util.UUID;

/**
 * 身份登记的<b>冻结输入</b>（Java→Worker 身份结果合同的一部分）。
 *
 * <p>字段全部来自<b>既有</b>数据：{@code assessmentId}/{@code processingRevision}/{@code photoVersion}
 * 取自 T05 {@code skin_assessments}（{@code V1__create_tables.sql:179,183,184}），三个参考图 media id
 * 取自 T11，{@code policyVersion}/{@code modelVersion}/{@code libraryRevision} 取自人脸服务
 * {@code search}/{@code health} 响应。{@code correlationId} 与 {@code providerRequestId} <b>必须</b>由
 * {@link IdentityResultContract} 的确定性派生得到，不得由调用方随机生成（否则跨重试无法对账）。
 *
 * <p><b>刻意不携带图片字节</b>：命令只带 media id，实现侧经既有存储读取路径取字节
 * （与 {@code MemberAccessGrantService.readStored} 同范式）。这样命令本身可审计、可日志化，
 * 且 media id 恰是要落进 {@code identity_summary.reference_media} 的值——D 的
 * {@code media_cleanup.py:71-78} 依赖该处出现 media id 子串来避免误删参考照。
 *
 * @param identityNamespace        身份库命名空间（人脸库隔离边界；配置项，绝不外发）
 * @param assessmentId             来源测肤任务 id（T05 主键）
 * @param processingRevision       <b>围栏</b>：登记所依据的处理代次
 * @param photoVersion             <b>围栏</b>：登记所依据的照片版本
 * @param referenceMediaFront      正脸参考图 media id（T11）
 * @param referenceMediaLeft       左侧参考图 media id
 * @param referenceMediaRight      右侧参考图 media id
 * @param correlationId            跨重试稳定的关联标识（{@link IdentityResultContract#enrollCorrelationId}）
 * @param providerRequestId        跨重试稳定的供应商请求标识（{@link IdentityResultContract#providerRequestId}）
 * @param providerConfigRevision   供应商配置修订（审计用；不含任何凭据）
 * @param policyVersion            本次搜索判定所用的服务端阈值策略版本（如 {@code search-v1}）
 * @param modelVersion             本次判定所用的模型版本
 * @param libraryRevision          本次判定所依据的人脸库修订号
 * @param searchDecision           本次 1:N 搜索的保守分类字面值（{@code matched}/{@code no_match}/{@code uncertain}）
 */
public record IdentityEnrollmentCommand(
        String identityNamespace,
        UUID assessmentId,
        long processingRevision,
        long photoVersion,
        String referenceMediaFront,
        String referenceMediaLeft,
        String referenceMediaRight,
        String correlationId,
        String providerRequestId,
        String providerConfigRevision,
        String policyVersion,
        String modelVersion,
        long libraryRevision,
        String searchDecision) {

    public IdentityEnrollmentCommand {
        requireText(identityNamespace, "identityNamespace");
        if (assessmentId == null) {
            throw new IllegalArgumentException("assessmentId must not be null");
        }
        if (processingRevision < 0) {
            // 与 DB CHECK ck_assessment_processing_revision (>= 0) 一致
            throw new IllegalArgumentException("processingRevision must be >= 0");
        }
        if (photoVersion <= 0) {
            // 与 DB CHECK ck_assessment_current_photo_version (> 0) 一致
            throw new IllegalArgumentException("photoVersion must be > 0");
        }
        requireText(referenceMediaFront, "referenceMediaFront");
        requireText(referenceMediaLeft, "referenceMediaLeft");
        requireText(referenceMediaRight, "referenceMediaRight");
        requireText(correlationId, "correlationId");
        requireText(providerRequestId, "providerRequestId");
        requireText(providerConfigRevision, "providerConfigRevision");
        requireText(policyVersion, "policyVersion");
        requireText(modelVersion, "modelVersion");
        requireText(searchDecision, "searchDecision");
        if (libraryRevision < 0) {
            throw new IllegalArgumentException("libraryRevision must be >= 0");
        }
    }

    /** 确定性人脸主体引用（= {@code members.face_subject_ref}）。 */
    public String faceSubjectRef() {
        return IdentityResultContract.candidateEntityId(identityNamespace, assessmentId);
    }

    private static void requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }
}

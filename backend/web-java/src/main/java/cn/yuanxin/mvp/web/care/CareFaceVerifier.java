package cn.yuanxin.mvp.web.care;

import java.util.UUID;

/**
 * 护理准入的人脸 1:1 核验端口（针对明确成员的<b>可信参考照</b>）。
 *
 * <p>总协调裁定 2026-09-11：公共 {@code FaceProvider.classify(purpose, bytes)}
 * 没有成员参数，无法证明「当前人脸 = 方案成员」，<b>不得</b>作为准入证据。
 * 本端口要求调用方显式给出目标 {@code memberId}，由实现方用该成员的可信参考照
 * 做 1:1 比对；成员绑定能力接入前，生产路径必须 fail-closed。</p>
 *
 * <p>最小公共接口需求（记录于 backend/handoffs/C.md）：</p>
 * <ul>
 *   <li>{@code verifyOneToOne(purpose, memberId, candidate)} → Outcome；</li>
 *   <li>实现方须能访问成员可信参考照与参考照版本/策略元数据；</li>
 *   <li>缺少成员绑定或参考照时返回 {@link Outcome#CAPABILITY_UNAVAILABLE}，
 *       绝不默认 MATCHED。</li>
 * </ul>
 */
public interface CareFaceVerifier {

    /** 1:1 核验结果；语义与错误映射见 {@link CareAdmissionService}。 */
    enum Outcome {
        MATCHED,
        MISMATCH,
        UNCERTAIN,
        QUALITY_REJECTED,
        DEPENDENCY_FAILED,
        /** 无成员绑定 1:1 能力（生产默认 fail-closed）。 */
        CAPABILITY_UNAVAILABLE
    }

    /**
     * 对候选人脸字节与指定成员的可信参考照做 1:1 比对。
     *
     * @param purpose   采集用途（admission / revalidation）
     * @param memberId  必须比对的目标成员（来自 T06/T07，非客户端输入）
     * @param candidate 当前人脸原始字节
     */
    Outcome verifyOneToOne(String purpose, UUID memberId, byte[] candidate);
}

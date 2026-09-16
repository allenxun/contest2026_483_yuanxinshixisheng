package cn.yuanxin.mvp.web.face;

/**
 * <b>照片比对</b>结果：仅证明"两张照片/照片与登记特征在算法上相似"，<b>无防翻拍能力</b>。
 *
 * <p>权威依据：{@code backend/doc/人脸服务调研与推荐方案-V1-MVP.md:31}「身份相似度<b>不证明现场性</b>；
 * 仅上传照片不能当完整防重放协议」与 {@code :179}「当前服务没有活体能力，相似度不能证明现场性」。
 *
 * <p><b>使用限制（硬性）</b>：本类型<b>不得</b>用于任何要求活体/防翻拍的准入判定，特别是护理准入
 * （{@code care/CareFaceVerifier}）。护理路径只接受 {@link LivenessVerifiedMatch}。
 * 这两种语义在<b>类型层面</b>分离，任何混用都会导致编译失败——这是刻意设计，不是冗余。
 *
 * <p>MVP 阶段本类型服务的"普通身份 1:1"能力属于<b>照片比对</b>：可用于"已登记主体的同人核验"
 * 这类不要求现场性的场景，必须在对外文档与 Swagger 说明中如实标注"照片比对，无防翻拍能力"。
 *
 * @param matched     是否判定为同一人（照片层面）
 * @param similarity  相似度（有限数值）
 * @param threshold   本次判定所用阈值（由服务端固定策略决定，调用方不可指定）
 * @param subjectRef  被比对的登记主体引用；内部使用，绝不外发、绝不入日志
 * @param requestId   服务端请求标识，用于对账
 */
public record PhotoComparisonMatch(
        boolean matched,
        double similarity,
        double threshold,
        String subjectRef,
        String requestId) {

    public PhotoComparisonMatch {
        if (!Double.isFinite(similarity)) {
            throw new IllegalArgumentException("similarity must be finite");
        }
        if (!Double.isFinite(threshold)) {
            throw new IllegalArgumentException("threshold must be finite");
        }
        if (subjectRef == null || subjectRef.isBlank()) {
            throw new IllegalArgumentException("subjectRef must not be blank");
        }
    }
}

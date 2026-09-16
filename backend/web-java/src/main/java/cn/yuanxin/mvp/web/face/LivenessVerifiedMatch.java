package cn.yuanxin.mvp.web.face;

/**
 * <b>经活体校验</b>的 1:1 结果：除照片相似外，还证明本次样本通过了服务端活体判定。
 *
 * <p><b>当前不可获得</b>：所接入的人脸服务（InsightFace {@code buffalo_l}）<b>没有活体模型</b>，
 * 恒返回 {@code liveness.supported=false}。客户端在"请求要求活体"时恒发送
 * {@code require_liveness=true}，服务端据此返回 501 {@code LIVENESS_UNSUPPORTED}；
 * 即便将来服务端声称 {@code supported=true}，也<b>必须</b>同时给出本次样本的
 * {@code liveness.passed=true}（JSON boolean），否则按 {@code LIVENESS_NOT_PASSED} 拒绝。
 * 因此本类型的实例在真实服务上<b>今天无法产生</b>，这是刻意的 fail-closed。
 *
 * <p><b>使用限制（硬性）</b>：护理准入（{@code care/CareFaceVerifier}）<b>只</b>接受本类型。
 * {@link PhotoComparisonMatch} 不能替代它——两种语义在类型层面分离，混用会编译失败。
 * 绝不允许"为了功能可用"而让护理路径接受照片比对结果，也不得新增任何"跳过活体"的开关。
 *
 * @param matched     是否判定为同一人（含活体通过）
 * @param similarity  相似度（有限数值）
 * @param threshold   本次判定所用阈值
 * @param subjectRef  被比对的登记主体引用；内部使用，绝不外发、绝不入日志
 * @param requestId   服务端请求标识，用于对账
 */
public record LivenessVerifiedMatch(
        boolean matched,
        double similarity,
        double threshold,
        String subjectRef,
        String requestId) {

    public LivenessVerifiedMatch {
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

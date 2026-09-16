package cn.yuanxin.mvp.web.face;

/**
 * 1:N 搜索的端口级结果（供应商无关；业务层只依赖本类型与 {@link FaceSearchDecision}）。
 *
 * <p><b>候选最小披露</b>：只有 {@link FaceSearchDecision#MATCHED} 才携带 {@code subjectRef}；
 * 任何情况下都<b>不</b>返回候选列表、不返回非命中主体的标识、不返回特征向量（embedding）。
 * 这与人脸服务侧的响应契约一致（见 {@code .coordination/B-work/face-round/spec-face-service.md} §1.3）。
 *
 * @param decision        保守分类，绝不为 null
 * @param subjectRef      命中主体的稳定引用；<b>仅</b>在 {@code decision == MATCHED} 时非 null。
 *                        该值属内部身份引用，<b>绝不</b>返回给 APP/云台等外部客户端，也不得写入日志
 * @param similarity      命中相似度；仅 MATCHED 时非 null（未命中/不确定不返回任何分数，避免被用于调参探测）
 * @param policyVersion   服务端阈值策略版本（例如 {@code search-v1}）；用于审计"本次判定依据哪套策略"
 * @param libraryRevision 本次判定所依据的人脸库修订号（一致快照）；用于审计
 * @param requestId       服务端请求标识，用于跨系统对账；不含身份信息
 */
public record FaceSearchResult(
        FaceSearchDecision decision,
        String subjectRef,
        Double similarity,
        String policyVersion,
        Long libraryRevision,
        String requestId) {

    public FaceSearchResult {
        if (decision == null) {
            throw new IllegalArgumentException("decision must not be null");
        }
        if (decision == FaceSearchDecision.MATCHED) {
            if (subjectRef == null || subjectRef.isBlank()) {
                throw new IllegalArgumentException("MATCHED requires a non-blank subjectRef");
            }
        } else if (subjectRef != null) {
            // 未命中/不确定却带 subjectRef 是契约违规：宁可失败，也不让调用方误以为拿到了身份。
            throw new IllegalArgumentException("subjectRef must be null unless decision is MATCHED");
        }
    }

    /** 是否为可用于后续只读成员定位的可靠命中。 */
    public boolean matched() {
        return decision == FaceSearchDecision.MATCHED && subjectRef != null && !subjectRef.isBlank();
    }
}

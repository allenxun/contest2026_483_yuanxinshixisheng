package cn.yuanxin.mvp.web.face;

/**
 * 人脸主体<b>只读</b>视图（供应商无关）。<b>内部使用</b>：其中的 {@code subjectRef} 是内部身份引用，
 * <b>绝不</b>外发给 APP/云台，<b>绝不</b>写入日志或异常消息。
 *
 * @param subjectRef      主体稳定引用（仅内部）
 * @param createdAt       服务端记录的创建时间
 * @param libraryRevision 查询时的库修订号
 */
public record FaceSubjectView(
        String subjectRef,
        String createdAt,
        long libraryRevision) {

    public FaceSubjectView {
        if (subjectRef == null || subjectRef.isBlank()) {
            throw new IllegalArgumentException("subjectRef must not be blank");
        }
    }
}
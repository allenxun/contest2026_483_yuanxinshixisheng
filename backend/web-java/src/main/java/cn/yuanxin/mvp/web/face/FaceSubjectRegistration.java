package cn.yuanxin.mvp.web.face;

/**
 * 人脸主体<b>登记</b>视图（供应商无关）。<b>内部使用</b>：其中的 {@code subjectRef} 是内部身份引用，
 * <b>绝不</b>外发给 APP/云台，<b>绝不</b>写入日志或异常消息。
 *
 * @param subjectRef      被登记主体的稳定引用（由调用方预先确定，非服务端随机生成）
 * @param libraryRevision 登记后的库修订号
 * @param createdAt       服务端记录的创建时间
 * @param requestId       服务端请求标识，用于对账
 */
public record FaceSubjectRegistration(
        String subjectRef,
        long libraryRevision,
        String createdAt,
        String requestId) {

    public FaceSubjectRegistration {
        if (subjectRef == null || subjectRef.isBlank()) {
            throw new IllegalArgumentException("subjectRef must not be blank");
        }
    }
}
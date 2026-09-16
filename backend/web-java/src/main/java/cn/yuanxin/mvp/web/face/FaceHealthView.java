package cn.yuanxin.mvp.web.face;

/**
 * 人脸服务<b>只读自省</b>视图（供应商无关；B 内部使用，绝不外发给 APP/云台）。
 *
 * <p>{@code livenessSupported} 必须<b>如实</b>来自服务端 {@code liveness.supported}，
 * 绝不允许硬编码 {@code true}——活体能力是安全声明，不是可用性开关。</p>
 *
 * <p>{@code libraryRevision} 是服务端人脸库修订号（一致快照），用于审计"某次判定依据哪一版库"。</p>
 *
 * @param status           服务端状态字符串（如 {@code ok}/{@code degraded}）
 * @param modelVersion     模型版本标识
 * @param modelLoaded      模型是否已加载
 * @param livenessSupported 服务端是否具备活体能力（如实，绝不硬编码 true）
 * @param libraryRevision  人脸库修订号
 */
public record FaceHealthView(
        String status,
        String modelVersion,
        boolean modelLoaded,
        boolean livenessSupported,
        long libraryRevision) {
}
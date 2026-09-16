package cn.yuanxin.mvp.web.face;

import java.util.List;

/**
 * 人脸服务<b>零写入</b>质量评估视图（供应商无关；B 内部使用，绝不外发给 APP/云台）。
 *
 * <p><b>诚实性要求</b>：{@code livenessSupported} 必须如实来自服务端
 * {@code liveness.supported}；服务端不具备的信号绝不用检测分数/相似度冒充。</p>
 *
 * @param faceCount         检出人脸数
 * @param minAcceptable     最大人脸的 {@code quality.min_acceptable}（是否达到服务端质量门槛）
 * @param reasons           质量原因列表；<b>不可为 null</b>（可为空列表）
 * @param livenessSupported 服务端是否具备活体能力（如实）
 * @param requestId         服务端请求标识，用于对账
 */
public record FaceQualityView(
        int faceCount,
        boolean minAcceptable,
        List<String> reasons,
        boolean livenessSupported,
        String requestId) {

    public FaceQualityView {
        if (faceCount < 0) {
            throw new IllegalArgumentException("faceCount must be >= 0");
        }
        if (reasons == null) {
            throw new IllegalArgumentException("reasons must not be null (use an empty list)");
        }
        reasons = List.copyOf(reasons);
    }
}
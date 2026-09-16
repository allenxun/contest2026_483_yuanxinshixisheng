package cn.yuanxin.mvp.web.face;

/**
 * 人脸服务<b>零写入</b>提取视图（供应商无关；B 内部使用，绝不外发给 APP/云台）。
 *
 * @param faceCount 检出人脸数（{@code >= 0}）
 * @param requestId 服务端请求标识，用于对账
 */
public record FaceExtractView(int faceCount, String requestId) {

    public FaceExtractView {
        if (faceCount < 0) {
            throw new IllegalArgumentException("faceCount must be >= 0");
        }
    }
}
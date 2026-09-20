package cn.yuanxin.mvp.web.face;

/**
 * 远端人脸服务调用失败。消息只含类别、服务错误码、request_id 与 HTTP 状态；
 * <b>不含</b> token、图像字节、embedding 或其它敏感内容。
 */
public class FaceServiceException extends RuntimeException {

    private final FaceServiceError error;
    private final FaceServiceFailureKind kind;

    public FaceServiceException(FaceServiceError error) {
        super(buildMessage(error));
        this.error = error;
        this.kind = FaceServiceFailureKind.classify(error.httpStatus(), error.code());
    }

    public FaceServiceError error() {
        return error;
    }

    public FaceServiceFailureKind kind() {
        return kind;
    }

    private static String buildMessage(FaceServiceError error) {
        return "face service failure (kind="
                + FaceServiceFailureKind.classify(error.httpStatus(), error.code())
                + ", code=" + error.safeCode()
                + ", http=" + error.httpStatus()
                + ", requestId=" + (error.requestId() == null || error.requestId().isBlank()
                        ? "<none>" : error.requestId())
                + ")";
    }
}

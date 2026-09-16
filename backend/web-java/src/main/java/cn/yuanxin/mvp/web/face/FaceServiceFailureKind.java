package cn.yuanxin.mvp.web.face;

import java.util.Set;

/**
 * 人脸服务失败分类：把 HTTP 状态 + 服务错误码映射为
 * 配置错误（不可重试）/ 能力不可用 / 依赖故障（可重试）。
 *
 * <p>质量类码（{@code NO_FACE}/{@code MULTI_FACES_AMBIGUOUS}/{@code IMAGE_DECODE_FAILED}/
 * {@code QUALITY_INSUFFICIENT}）由适配器<b>先于</b>本分类识别为图像质量问题，不在这里归为
 * 配置错误。</p>
 */
public enum FaceServiceFailureKind {

    CONFIGURATION,
    CAPABILITY,
    DEPENDENCY;

    static final Set<String> CAPABILITY_CODES = Set.of(
            "SUBJECT_NOT_FOUND",
            "NAMESPACE_NOT_FOUND",
            "LIVENESS_UNSUPPORTED");

    static final Set<String> CONFIGURATION_CODES = Set.of(
            "UNAUTHORIZED",
            "UNSUPPORTED_MEDIA_TYPE",
            "IMAGE_TOO_LARGE",
            "INVALID_REQUEST",
            "SUBJECT_ALREADY_EXISTS");

    static final Set<String> DEPENDENCY_CODES = Set.of(
            "MODEL_UNAVAILABLE",
            "MODEL_NOT_LOADED",
            "CONCURRENCY_LIMIT",
            "INFERENCE_TIMEOUT",
            "INTERNAL_ERROR",
            // 存储（SQLite）不可达：/ready 专用，属依赖故障而非模型/能力问题。
            "STORE_UNAVAILABLE");

    public static FaceServiceFailureKind classify(int httpStatus, String code) {
        String normalized = code == null ? "" : code.trim();
        if (CAPABILITY_CODES.contains(normalized)) {
            return CAPABILITY;
        }
        if (CONFIGURATION_CODES.contains(normalized)) {
            return CONFIGURATION;
        }
        if (DEPENDENCY_CODES.contains(normalized)) {
            return DEPENDENCY;
        }
        if (httpStatus == 401 || httpStatus == 413 || httpStatus == 415) {
            return CONFIGURATION;
        }
        if (httpStatus == 404 || httpStatus == 409 || httpStatus == 422 || httpStatus == 501) {
            return CAPABILITY;
        }
        if (httpStatus == 429 || httpStatus >= 500) {
            return DEPENDENCY;
        }
        if (httpStatus == 400) {
            // 其余 400 视为参数/配置问题（质量类码已被适配器提前识别）。
            return CONFIGURATION;
        }
        return DEPENDENCY;
    }
}

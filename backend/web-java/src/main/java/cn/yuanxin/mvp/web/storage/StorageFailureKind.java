package cn.yuanxin.mvp.web.storage;

import java.util.Set;

/**
 * 阿里云 OSS 失败分类（把 SDK 错误码映射为"配置错误（不可重试）"与"依赖故障（可重试）"）。
 * {@code NoSuchKey} 不属于本分类——它由 {@link OssStorageAdapter} 单独映射为"对象不存在"语义。
 */
public enum StorageFailureKind {

    /** 配置/权限错误：签名、密钥、时间偏移、参数等；重试无意义。 */
    CONFIGURATION,
    /** 依赖故障：网络、超时、5xx/服务端错误；可退避重试。 */
    DEPENDENCY;

    private static final Set<String> CONFIGURATION_CODES = Set.of(
            "AccessDenied",
            "InvalidAccessKeyId",
            "InvalidAccessKeyId.NotFound",
            "AccessKeyDisabled",
            "SignatureDoesNotMatch",
            "RequestTimeTooSkewed",
            "NoSuchBucket",
            "InvalidBucketName",
            "InvalidArgument",
            "InvalidRequest",
            "InvalidObjectName",
            "MissingContentLength",
            "MissingSecurityToken",
            "InvalidSecurityToken",
            "SecurityTokenExpired",
            "IllegalTimestamp",
            "MissingArgument");

    /** 未知/空码保守归为依赖类（可观察后重试），绝不视为成功。 */
    public static StorageFailureKind classify(String errorCode) {
        if (errorCode == null || errorCode.isBlank()) {
            return DEPENDENCY;
        }
        return CONFIGURATION_CODES.contains(errorCode.trim()) ? CONFIGURATION : DEPENDENCY;
    }
}

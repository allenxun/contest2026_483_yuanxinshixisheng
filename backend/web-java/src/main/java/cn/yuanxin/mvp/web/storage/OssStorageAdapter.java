package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.media.StoragePort;
import com.aliyun.oss.ClientException;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSException;
import com.aliyun.oss.model.ObjectMetadata;
import com.aliyun.oss.model.OSSObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;

/**
 * 阿里云 OSS {@link StoragePort} 真实适配器（<b>唯一</b>接触 {@code com.aliyun.oss.*} SDK 的实现）。
 * 私有桶、流式读写、无公开 URL（<b>不</b>调用 {@code generatePresignedUrl}）。
 *
 * <p><b>对象不存在语义</b>：{@code getStream}/{@code get} 在 OSS 返回 {@code NoSuchKey} 时返回
 * {@code null}（与端口一致）；其它异常一律抛出，<b>绝不</b>用 {@code null} 冒充"不存在"。</p>
 *
 * <p><b>put 元数据</b>：写入真实 {@code Content-Type} 与 {@code Content-Length}，并加
 * {@code x-oss-meta-purpose}（值取自 objectKey 第二段 purpose；不含任何身份信息）。</p>
 *
 * <p><b>失败映射</b>：{@link StorageFailureKind#CONFIGURATION}（{@code AccessDenied}/
 * {@code InvalidAccessKeyId}/{@code SignatureDoesNotMatch}/{@code RequestTimeTooSkewed}/参数类）
 * → 503 <b>不可重试</b>；{@link StorageFailureKind#DEPENDENCY}（{@code ClientException}/网络/
 * 超时/5xx）→ 503 <b>可重试</b>。<b>不得</b>静默成功、<b>不得</b>回退本地文件系统。</p>
 *
 * <p><b>日志脱敏</b>：只记 op、OSS 业务错误码与 RequestId；绝不记 AK/SK/token、bucket/endpoint、
 * 对象内容。</p>
 */
public class OssStorageAdapter implements StoragePort {

    private static final Logger log = LoggerFactory.getLogger(OssStorageAdapter.class);
    private static final String META_PURPOSE_KEY = "purpose";

    private final OSS oss;
    private final String bucket;

    public OssStorageAdapter(OSS oss, String bucket) {
        this.oss = oss;
        this.bucket = bucket;
    }

    @Override
    public void put(String objectKey, InputStream content, long byteSize, String contentType) {
        ObjectMetadata metadata = new ObjectMetadata();
        metadata.setContentLength(byteSize);
        metadata.setContentType(contentType == null || contentType.isBlank()
                ? "application/octet-stream" : contentType);
        String purpose = purposeOf(objectKey);
        if (purpose != null) {
            metadata.addUserMetadata(META_PURPOSE_KEY, purpose);
        }
        try {
            oss.putObject(bucket, objectKey, content, metadata);
        } catch (OSSException serverFailure) {
            throw mapOssFailure("put", serverFailure);
        } catch (ClientException clientFailure) {
            throw dependencyFailure("put", clientFailure);
        }
    }

    @Override
    public InputStream getStream(String objectKey) {
        try {
            OSSObject object = oss.getObject(bucket, objectKey);
            return object == null ? null : object.getObjectContent();
        } catch (OSSException serverFailure) {
            if (isNoSuchKey(serverFailure)) {
                return null;
            }
            throw mapOssFailure("getStream", serverFailure);
        } catch (ClientException clientFailure) {
            throw dependencyFailure("getStream", clientFailure);
        }
    }

    @Override
    public byte[] get(String objectKey) {
        try (InputStream in = getStream(objectKey)) {
            return in == null ? null : in.readAllBytes();
        } catch (IOException ioFailure) {
            throw new UncheckedIOException("storage read failed", ioFailure);
        }
    }

    @Override
    public boolean exists(String objectKey) {
        try {
            return oss.doesObjectExist(bucket, objectKey);
        } catch (OSSException serverFailure) {
            if (isNoSuchKey(serverFailure)) {
                return false;
            }
            throw mapOssFailure("exists", serverFailure);
        } catch (ClientException clientFailure) {
            throw dependencyFailure("exists", clientFailure);
        }
    }

    @Override
    public void delete(String objectKey) {
        try {
            oss.deleteObject(bucket, objectKey);
        } catch (OSSException serverFailure) {
            // delete 幂等：对象本就不存在视为成功。
            if (!isNoSuchKey(serverFailure)) {
                throw mapOssFailure("delete", serverFailure);
            }
        } catch (ClientException clientFailure) {
            throw dependencyFailure("delete", clientFailure);
        }
    }

    private ApiException mapOssFailure(String operation, OSSException failure) {
        StorageFailureKind kind = StorageFailureKind.classify(failure.getErrorCode());
        String safeCode = safe(failure.getErrorCode());
        String safeRequestId = safe(failure.getRequestId());
        if (kind == StorageFailureKind.CONFIGURATION) {
            log.warn("oss configuration error op={} code={} requestId={}",
                    operation, safeCode, safeRequestId);
            return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE, 503, false,
                    "storage configuration error (op=" + operation + ", code=" + safeCode
                            + ", requestId=" + safeRequestId + "); not retryable",
                    null, null);
        }
        log.warn("oss dependency failure op={} code={} requestId={}",
                operation, safeCode, safeRequestId);
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE, 503, true,
                "storage dependency failure (op=" + operation + ", code=" + safeCode
                        + ", requestId=" + safeRequestId + "); retry with backoff",
                null, null);
    }

    private ApiException dependencyFailure(String operation, ClientException failure) {
        String exceptionName = failure.getClass().getSimpleName();
        log.warn("oss client/transport failure op={} exception={}", operation, exceptionName);
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE, 503, true,
                "storage dependency failure (op=" + operation + ", exception=" + exceptionName
                        + "); retry with backoff",
                null, null);
    }

    private static boolean isNoSuchKey(OSSException failure) {
        return "NoSuchKey".equalsIgnoreCase(failure.getErrorCode());
    }

    /** object key 布局 {@code <env>/<purpose>/<uuid>}：取第二段 purpose。 */
    private static String purposeOf(String objectKey) {
        if (objectKey == null) {
            return null;
        }
        String[] parts = objectKey.split("/");
        return parts.length >= 2 ? parts[1] : null;
    }

    private static String safe(String value) {
        return value == null ? "<none>" : value;
    }
}

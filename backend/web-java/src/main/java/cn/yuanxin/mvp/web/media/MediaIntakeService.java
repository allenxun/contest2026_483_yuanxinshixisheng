package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.idempotency.CanonicalObjectBuilder;
import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * multipart 图片受理助手（DD 10.1 上传流程的公共扩展点）：
 * 逐 part 流式摘要 → T11 pending → StoragePort 写入 → 校验标 available。
 *
 * <p>B/C/D 业务接线：先 {@link #digest} 计算逐 part 摘要组装 canonicalObject 做
 * T13 begin，再 {@link #ingest} 落存储与元数据，最后在受理事务补 T11 归属并
 * completeSuccess（“available ≠ 可访问”由 MediaAccessPolicy 在读取时裁决）。</p>
 */
@Service
public class MediaIntakeService {

    private final MediaService mediaService;
    private final StoragePort storage;

    public MediaIntakeService(MediaService mediaService, StoragePort storage) {
        this.mediaService = mediaService;
        this.storage = storage;
    }

    public record IngestedMedia(String part, MediaObject media, String sha256Hex,
                                String contentType, long byteSize) {
    }

    /** 计算单 part 原始字节 SHA-256（小写 hex），不消费流以外的语义。 */
    public static String sha256Hex(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    /**
     * 受理一批图片 part：每个 part 建立 pending 行、写入 StoragePort、
     * 校验实际格式/大小后标 available。校验失败 → failed + last_error 并抛出。
     *
     * @param parts part 名 → 原始字节（metadata part 不属于这里）
     */
    public Map<String, IngestedMedia> ingest(PrincipalContext principal, MediaPurpose purpose,
                                             UUID t13RequestId, Map<String, byte[]> parts) {
        Map<String, IngestedMedia> out = new LinkedHashMap<>();
        for (Map.Entry<String, byte[]> entry : parts.entrySet()) {
            String partName = entry.getKey();
            byte[] bytes = entry.getValue();
            String sha = sha256Hex(bytes);
            MediaObject pending = mediaService.createPending(purpose,
                    principal.principalType().name().toLowerCase(),
                    principal.t13PrincipalId(), t13RequestId);
            String detected;
            try {
                detected = sniffImageContentType(bytes);
                storage.put(pending.objectKey(), new ByteArrayInputStream(bytes), bytes.length,
                        detected == null ? "application/octet-stream" : detected);
                MediaObject available = mediaService.markAvailable(pending.id(), detected,
                        bytes.length, sha);
                out.put(partName, new IngestedMedia(partName, available, sha, detected, bytes.length));
            } catch (ApiException e) {
                mediaService.fail(pending.id(), e.getCode(), e.getMessage());
                throw e;
            } catch (RuntimeException e) {
                mediaService.fail(pending.id(), ErrorCode.DEPENDENCY_UNAVAILABLE,
                        "storage write failed");
                throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE, "storage write failed");
            }
        }
        return out;
    }

    /** canonicalObject 的 imageParts 摘要项（part 名 + 内容 SHA-256）。 */
    public static List<CanonicalObjectBuilder.PartDigest> partDigests(Map<String, byte[]> parts) {
        return parts.entrySet().stream()
                .map(e -> new CanonicalObjectBuilder.PartDigest(e.getKey(), sha256Hex(e.getValue())))
                .toList();
    }

    /** 实际格式嗅探（非仅 MIME 声明）；白名单外 → UNSUPPORTED_IMAGE。 */
    public static String sniffImageContentType(byte[] b) {
        if (b.length >= 3 && (b[0] & 0xFF) == 0xFF && (b[1] & 0xFF) == 0xD8 && (b[2] & 0xFF) == 0xFF) {
            return "image/jpeg";
        }
        if (b.length >= 8 && (b[0] & 0xFF) == 0x89 && b[1] == 'P' && b[2] == 'N' && b[3] == 'G') {
            return "image/png";
        }
        if (b.length >= 4 && b[0] == 'G' && b[1] == 'I' && b[2] == 'F' && b[3] == '8') {
            return "image/gif";
        }
        if (b.length >= 12 && b[0] == 'R' && b[1] == 'I' && b[2] == 'F' && b[3] == 'F'
                && b[8] == 'W' && b[9] == 'E' && b[10] == 'B' && b[11] == 'P') {
            return "image/webp";
        }
        throw new ApiException(ErrorCode.UNSUPPORTED_IMAGE, "not a supported image format");
    }
}

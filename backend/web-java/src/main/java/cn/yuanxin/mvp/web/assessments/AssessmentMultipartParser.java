package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.MultiValueMap;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * M3-A01/M3-A02 multipart 严格解析（DD 3.3/10.1；contracts M3A01Metadata/
 * M3A02Metadata）：metadata part（application/json，未知字段拒绝）+ 二进制
 * 图片 part。缺 part / 多 part / 非法字段一律 400 INVALID_INPUT；三图合计超
 * 限 413 UPLOAD_TOO_LARGE。
 */
@Component
public class AssessmentMultipartParser {

    private static final Pattern BIGINT = Pattern.compile("^(0|[1-9][0-9]*)$");
    private static final Set<String> VIEWS = Set.of("front", "left", "right");

    private final ObjectMapper mapper;
    private final long maxRequestBytes;

    public AssessmentMultipartParser(ObjectMapper mapper,
                                     @Value("${app.assessments.max-request-bytes:33554432}")
                                     long maxRequestBytes) {
        this.mapper = mapper;
        this.maxRequestBytes = maxRequestBytes;
    }

    public record A01Metadata(String photoVersion, String captureSessionId, String consentEvidenceRef) {
    }

    public record A02Metadata(String expectedPhotoVersion, List<String> replacedViews) {
    }

    public record ParsedA01(A01Metadata metadata, Map<String, byte[]> images) {
    }

    public record ParsedA02(A02Metadata metadata, Map<String, byte[]> images) {
    }

    public ParsedA01 parseA01(HttpServletRequest request) {
        RawParts raw = split(request);
        A01Metadata md = readMetadata(raw.metadataBytes(), A01Metadata.class);
        if (!BIGINT.matcher(nullToEmpty(md.photoVersion())).matches() || !"1".equals(md.photoVersion())) {
            throw invalid("photoVersion must be the bigint string \"1\" for a new task");
        }
        requireText(md.captureSessionId(), "captureSessionId", 128);
        requireText(md.consentEvidenceRef(), "consentEvidenceRef", 128);
        Map<String, byte[]> images = requireExactViews(raw.imageParts(), VIEWS, "front,left,right");
        checkTotalSize(images);
        return new ParsedA01(md, images);
    }

    public ParsedA02 parseA02(HttpServletRequest request) {
        RawParts raw = split(request);
        A02Metadata md = readMetadata(raw.metadataBytes(), A02Metadata.class);
        if (md.expectedPhotoVersion() == null || !BIGINT.matcher(md.expectedPhotoVersion()).matches()) {
            throw invalid("expectedPhotoVersion must be a decimal bigint string");
        }
        List<String> replaced = md.replacedViews();
        if (replaced == null || replaced.isEmpty()) {
            throw invalid("replacedViews must be a non-empty list");
        }
        LinkedHashSet<String> requested = new LinkedHashSet<>();
        for (String view : replaced) {
            if (!VIEWS.contains(view)) {
                throw invalid("replacedViews entries must be one of front,left,right");
            }
            requested.add(view);
        }
        if (requested.size() != replaced.size()) {
            throw invalid("replacedViews must be unique");
        }
        Map<String, byte[]> images = requireExactViews(raw.imageParts(), requested,
                String.join(",", requested));
        checkTotalSize(images);
        return new ParsedA02(md, images);
    }

    private record RawParts(byte[] metadataBytes, Map<String, byte[]> imageParts) {
    }

    private RawParts split(HttpServletRequest request) {
        if (!(request instanceof MultipartHttpServletRequest multi)) {
            throw invalid("multipart/form-data request required");
        }
        MultiValueMap<String, MultipartFile> multiFiles = multi.getMultiFileMap();
        // getFileMap() 会把同名 part 静默折叠成单值，必须在折叠前按 part 名
        // 逐一检出重复（front/left/right/metadata 等），否则重复文件会被漏检。
        for (Map.Entry<String, List<MultipartFile>> e : multiFiles.entrySet()) {
            if (e.getValue().size() > 1) {
                throw invalid("duplicate multipart part: " + e.getKey());
            }
        }
        Map<String, byte[]> parts = new LinkedHashMap<>();
        for (Map.Entry<String, List<MultipartFile>> e : multiFiles.entrySet()) {
            if ("metadata".equals(e.getKey())) {
                continue;
            }
            try {
                parts.put(e.getKey(), e.getValue().get(0).getBytes());
            } catch (Exception ex) {
                throw invalid("unreadable multipart part: " + e.getKey());
            }
        }
        byte[] metadata = readMetadataPart(multiFiles);
        String[] metadataParams = multi.getParameterValues("metadata");
        int metadataParamCount = metadataParams == null ? 0 : metadataParams.length;
        // 同名 metadata 以文本参数重复 2+ 次，或同时以 file part + 文本参数两种
        // 形式出现，均视为重复 part → 400。
        if (metadataParamCount > 1) {
            throw invalid("duplicate multipart part: metadata");
        }
        if (metadata != null && metadataParamCount == 1) {
            throw invalid("duplicate multipart part: metadata");
        }
        if (metadata == null && metadataParamCount == 1) {
            metadata = metadataParams[0].getBytes(StandardCharsets.UTF_8);
        }
        if (metadata == null) {
            throw invalid("metadata part is required");
        }
        // 未声明的额外 multipart 文本参数同样拒绝（防未知字段静默成功）
        for (String name : multi.getParameterMap().keySet()) {
            if (!"metadata".equals(name)) {
                throw invalid("unknown multipart field: " + name);
            }
        }
        return new RawParts(metadata, parts);
    }

    /**
     * metadata 若为文件 part，其 Content-Type 必须是 application/json（容忍
     * charset 等参数后缀）；否则 400 INVALID_INPUT。文本参数形式的 metadata
     * 无 Content-Type，不在此校验。
     */
    private byte[] readMetadataPart(MultiValueMap<String, MultipartFile> multiFiles) {
        List<MultipartFile> metadataFiles = multiFiles.get("metadata");
        if (metadataFiles == null || metadataFiles.isEmpty()) {
            return null;
        }
        MultipartFile metadata = metadataFiles.get(0);
        MediaType mediaType = null;
        String contentType = metadata.getContentType();
        if (contentType != null) {
            try {
                mediaType = MediaType.parseMediaType(contentType);
            } catch (RuntimeException e) {
                mediaType = null;
            }
        }
        if (mediaType == null || !MediaType.APPLICATION_JSON.isCompatibleWith(mediaType)) {
            throw invalid("metadata part must be application/json");
        }
        try {
            return metadata.getBytes();
        } catch (Exception ex) {
            throw invalid("unreadable multipart part: metadata");
        }
    }

    private Map<String, byte[]> requireExactViews(Map<String, byte[]> parts, Set<String> expected,
                                                  String label) {
        if (!parts.keySet().equals(expected)) {
            List<String> missing = new ArrayList<>(expected);
            missing.removeAll(parts.keySet());
            List<String> extra = new ArrayList<>(parts.keySet());
            extra.removeAll(expected);
            throw invalid("image parts must be exactly [" + label + "]; missing=" + missing
                    + " extra=" + extra);
        }
        return parts;
    }

    private void checkTotalSize(Map<String, byte[]> images) {
        long total = 0;
        for (byte[] b : images.values()) {
            total += b.length;
            if (total > maxRequestBytes) {
                throw new ApiException(ErrorCode.UPLOAD_TOO_LARGE,
                        "total image bytes exceed configured limit " + maxRequestBytes);
            }
        }
    }

    private <T> T readMetadata(byte[] bytes, Class<T> type) {
        try {
            return mapper.readValue(bytes, type);
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw invalid("metadata is not a valid " + type.getSimpleName());
        }
    }

    private static void requireText(String value, String field, int max) {
        if (value == null || value.isEmpty()) {
            throw invalid(field + " is required");
        }
        if (value.length() > max) {
            throw invalid(field + " exceeds max length " + max);
        }
    }

    private static String nullToEmpty(String v) {
        return v == null ? "" : v;
    }

    private static ApiException invalid(String message) {
        return new ApiException(ErrorCode.INVALID_INPUT, message);
    }
}

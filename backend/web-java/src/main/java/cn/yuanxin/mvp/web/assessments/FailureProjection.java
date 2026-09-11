package cn.yuanxin.mvp.web.assessments;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * M3-A03 有界安全投影（总协调裁定 3；identity_result 唯一业务通道）：
 *
 * <ul>
 *   <li><b>requiredViews(status, identityResultJson)</b>：仅当
 *       {@code status='needs_retake'} 时，解析 Worker 属主的 T05.identity_result
 *       对象，读取 {@code quality.required_views} 数组，逐项过滤到
 *       [front,left,right] 枚举、去重、上限 3；任何缺失/非数组/解析失败 →
 *       空数组。绝不读取 failure_detail。</li>
 *   <li><b>retryable(failureCode)</b>：封闭映射。failureCode 为 null → null；
 *       任何非 null failure_code → false。当前 D Worker 终态码全部不可重试
 *       （QUALITY_REJECTED / NOT_SAME_PERSON / IDENTITY_UNCERTAIN /
 *       IDENTITY_ENROLLMENT_TIMEOUT / SOURCE_IMAGE_UNAVAILABLE /
 *       RESULT_ARCHIVE_FAILED / PROVIDER_CONTRACT_VIOLATION /
 *       MEMBER_NOT_VISIBLE / DEPENDENCY_UNAVAILABLE）。{@code true} 为未来
 *       允许瞬时可重试失败暴露预留；在此之前一律 false，绝不解析
 *       failure_detail/identity_result 推导重试性。</li>
 * </ul>
 */
@Component
public class FailureProjection {

    private static final Set<String> VIEWS = Set.of("front", "left", "right");
    private static final int MAX_REQUIRED_VIEWS = 3;

    private final ObjectMapper mapper;

    public FailureProjection(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    /**
     * 封闭 failure_code → retryable 映射：null（无失败）→ null；任何已公开的
     * 非 null failure_code → false（当前全部终态不可重试）。不读任何诊断列。
     */
    public Boolean retryable(String failureCode) {
        if (failureCode == null) {
            return null;
        }
        return false;
    }

    /**
     * 从 identity_result.quality.required_views 投影需补拍视角（仅 needs_retake）。
     */
    public List<String> requiredViews(String status, String identityResultJson) {
        if (!"needs_retake".equals(status)) {
            return List.of();
        }
        JsonNode root = parse(identityResultJson);
        if (root == null || !root.isObject()) {
            return List.of();
        }
        JsonNode required = root.path("quality").path("required_views");
        if (!required.isArray()) {
            return List.of();
        }
        LinkedHashSet<String> out = new LinkedHashSet<>();
        for (JsonNode item : required) {
            if (out.size() >= MAX_REQUIRED_VIEWS) {
                break;
            }
            if (item.isTextual() && VIEWS.contains(item.asText())) {
                out.add(item.asText());
            }
        }
        return new ArrayList<>(out);
    }

    private JsonNode parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return mapper.readTree(raw);
        } catch (Exception e) {
            return null;
        }
    }
}

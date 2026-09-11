package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * T05.photo_versions 读写助手（Java 写边界：受理/补拍构造版本清单）。
 *
 * <p>结构（DD 9.1 示例与 D 包裁定）：
 * {@code {"schema_version":1,"versions":[{"version":1,"images":{front,left,right},
 * "quality":{"status":"pending","required_views":[]}}]}}。quality 结论由 Python
 * worker 通过 identity_result 发布（Java 只读）；Java 在此只写 pending 占位。</p>
 */
@Component
public class PhotoVersions {

    private final ObjectMapper mapper;

    public PhotoVersions(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    /** 初始版本 1 的完整视角清单。 */
    public String initial(Map<String, String> images) {
        ObjectNode root = newRoot();
        ArrayNode versions = root.putArray("versions");
        appendVersion(versions, 1, images);
        return serialize(root);
    }

    /** 追加新版本（完整视角清单）。 */
    public String append(String existingJson, long newVersion, Map<String, String> images) {
        ObjectNode root = parseObject(existingJson);
        ArrayNode versions = root.withArray("versions");
        if (!versions.isArray()) {
            throw new ApiException(ErrorCode.INTERNAL, "photo_versions malformed");
        }
        appendVersion(versions, newVersion, images);
        return serialize(root);
    }

    /** 读取指定版本已接纳的视角→mediaId 映射（缺版本/缺键返回空对象）。 */
    public Map<String, String> imagesAtVersion(String existingJson, long version) {
        Map<String, String> out = new LinkedHashMap<>();
        JsonNode versions = parseObject(existingJson).path("versions");
        if (!versions.isArray()) {
            return out;
        }
        for (JsonNode v : versions) {
            if (v.path("version").asLong(-1) == version) {
                JsonNode images = v.path("images");
                if (images.isObject()) {
                    images.fields().forEachRemaining(e -> {
                        if (e.getValue().isTextual()) {
                            out.put(e.getKey(), e.getValue().asText());
                        }
                    });
                }
            }
        }
        return out;
    }

    private static void appendVersion(ArrayNode versions, long version, Map<String, String> images) {
        ObjectNode v = versions.addObject();
        v.put("version", version);
        ObjectNode imageNode = v.putObject("images");
        // 固定 front/left/right 顺序，保证 JSON 稳定
        for (String view : List.of("front", "left", "right")) {
            String mediaId = images.get(view);
            if (mediaId != null) {
                imageNode.put(view, mediaId);
            }
        }
        ObjectNode quality = v.putObject("quality");
        quality.put("status", "pending");
        quality.putArray("required_views");
    }

    private ObjectNode newRoot() {
        ObjectNode root = mapper.createObjectNode();
        root.put("schema_version", 1);
        return root;
    }

    private ObjectNode parseObject(String json) {
        if (json == null || json.isBlank()) {
            return newRoot();
        }
        try {
            JsonNode node = mapper.readTree(json);
            if (node instanceof ObjectNode obj) {
                return obj;
            }
        } catch (Exception e) {
            // fallthrough
        }
        throw new ApiException(ErrorCode.INTERNAL, "photo_versions malformed");
    }

    private String serialize(ObjectNode root) {
        try {
            return mapper.writeValueAsString(root);
        } catch (Exception e) {
            throw new ApiException(ErrorCode.INTERNAL, "photo_versions serialization failed");
        }
    }
}

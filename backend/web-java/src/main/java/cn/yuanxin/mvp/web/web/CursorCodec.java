package cn.yuanxin.mvp.web.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * 不透明游标编解码（契约公共规则：limit 默认 20 上限 100；cursor 绑定
 * 排序值+ID+筛选摘要；非法游标 400 INVALID_INPUT）。
 *
 * <p>编码 = URL-safe Base64(JSON {"k":排序值,"i":末位ID,"f":筛选摘要})。
 * 解码失败（非 Base64 / 非 JSON / 缺键）一律抛 {@link CursorException}。
 * B/C/D 列表端点直接复用。</p>
 */
@Component
public class CursorCodec {

    public static final int DEFAULT_LIMIT = 20;
    public static final int MAX_LIMIT = 100;

    private final ObjectMapper objectMapper;

    public CursorCodec(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public record Cursor(String sortValue, String id, String filterDigest) {
    }

    public String encode(String sortValue, String id, String filterDigest) {
        try {
            var node = objectMapper.createObjectNode();
            node.put("k", sortValue);
            node.put("i", id);
            node.put("f", filterDigest);
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(objectMapper.writeValueAsBytes(node));
        } catch (Exception e) {
            throw new IllegalStateException("cursor encode failed", e);
        }
    }

    public Cursor decode(String cursor) {
        try {
            byte[] raw = Base64.getUrlDecoder().decode(cursor.getBytes(StandardCharsets.UTF_8));
            JsonNode node = objectMapper.readTree(raw);
            if (!node.isObject() || !node.hasNonNull("k") || !node.hasNonNull("i")) {
                throw new CursorException("cursor missing required members");
            }
            return new Cursor(node.get("k").asText(), node.get("i").asText(),
                    node.hasNonNull("f") ? node.get("f").asText() : "");
        } catch (CursorException e) {
            throw e;
        } catch (Exception e) {
            throw new CursorException("cursor is not a valid opaque token");
        }
    }

    /** 校验 limit：缺省 20，越界（&lt;1 或 &gt;100）由调用方转 400。 */
    public int normalizeLimit(Integer limit) {
        if (limit == null) return DEFAULT_LIMIT;
        if (limit < 1 || limit > MAX_LIMIT) {
            throw new CursorException("limit must be between 1 and 100");
        }
        return limit;
    }
}

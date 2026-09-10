package cn.yuanxin.mvp.web.idempotency;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

/**
 * T13 payload_hash 的 canonicalObject 组装（DD 3.3 / contracts/canonicalization.md §2）。
 *
 * <p>固定形状（跨语言约定，B/C/D 必须一致）：</p>
 * <pre>
 * {
 *   "operation":  "system.echo.create" 等稳定逻辑操作标识,
 *   "pathParams": { 路径参数, 服务端规范形式(UUID 小写文本 / bigint 十进制字符串) },
 *   "fields":     { 语义字段 camelCase; 缺省值先展开为显式值(含 null); 有序数组不排序 },
 *   "imageParts": [ { "part": "face", "sha256": "小写hex" }, ... 按 part 名升序 ]
 * }
 * </pre>
 * <p>可变传输头（Authorization/X-Request-Id/multipart 边界/接收时间）一律不进；
 * Idempotency-Key 本身是唯一键组成部分，也不重复进。</p>
 */
public final class CanonicalObjectBuilder {

    private final String operation;
    private final ObjectNode root;

    private CanonicalObjectBuilder(String operation) {
        this.operation = operation;
        this.root = Jcs.objectNode();
        root.put("operation", operation);
        root.set("pathParams", Jcs.objectNode());
        root.set("fields", Jcs.objectNode());
        root.set("imageParts", Jcs.arrayNode());
    }

    public static CanonicalObjectBuilder forOperation(String operation) {
        return new CanonicalObjectBuilder(operation);
    }

    public CanonicalObjectBuilder pathParams(Map<String, ?> params) {
        ObjectNode node = (ObjectNode) root.get("pathParams");
        params.forEach((k, v) -> node.set(k, Jcs.toNode(v)));
        return this;
    }

    /** 语义字段；caller 负责把有默认语义的可选字段补齐为显式值（含 null）。 */
    public CanonicalObjectBuilder fields(Map<String, ?> semanticFields) {
        ObjectNode node = (ObjectNode) root.get("fields");
        semanticFields.forEach((k, v) -> node.set(k, Jcs.toNode(v)));
        return this;
    }

    /** multipart 图片：part 名 + 该 part 原始字节 SHA-256 小写 hex；按 part 名排序存入。 */
    public CanonicalObjectBuilder imageParts(List<PartDigest> parts) {
        ArrayNode arr = (ArrayNode) root.get("imageParts");
        parts.stream()
                .sorted(Comparator.comparing(PartDigest::part))
                .forEach(p -> {
                    ObjectNode e = arr.addObject();
                    e.put("part", p.part());
                    e.put("sha256", p.sha256Hex());
                });
        return this;
    }

    public JsonNode build() {
        return root;
    }

    /** canonical JCS 字节上的 SHA-256 小写 hex（T13 payload_hash 列值）。 */
    public String payloadHash() {
        return Jcs.sha256Hex(root);
    }

    public record PartDigest(String part, String sha256Hex) {
    }
}

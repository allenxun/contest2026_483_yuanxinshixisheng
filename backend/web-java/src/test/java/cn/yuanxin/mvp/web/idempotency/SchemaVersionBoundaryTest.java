package cn.yuanxin.mvp.web.idempotency;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * oracle round-2 R2-4 边界：IdempotencyService.ensureSchemaVersion 仅当缺失时
 * 注入整数 1；显式非整数版本（null/字符串/小数/对象/数组）→ 400 INVALID_INPUT；
 * 顶层非对象 → 400。锁定边界，防止 jsonb_typeof CHECK 触发数据库层 500。
 */
class SchemaVersionBoundaryTest {

    @Test
    @DisplayName("缺失 → 注入整数 1")
    void injectsIntegerWhenAbsent() {
        ObjectNode node = Jcs.objectNode();
        IdempotencyService.ensureSchemaVersion(node);
        assertTrue(node.path("schema_version").isIntegralNumber());
        assertEquals(1, node.path("schema_version").asInt());
    }

    @Test
    @DisplayName("显式整数版本原样保留")
    void preservesExplicitInteger() {
        ObjectNode node = Jcs.objectNode();
        node.put("schema_version", 7);
        IdempotencyService.ensureSchemaVersion(node);
        assertEquals(7, node.path("schema_version").asInt());
    }

    @Test
    @DisplayName("显式 null 版本 → 400 INVALID_INPUT")
    void rejectsNullVersion() {
        ObjectNode node = Jcs.objectNode();
        node.putNull("schema_version");
        assertInvalidInput(node);
    }

    @Test
    @DisplayName("显式字符串版本 → 400 INVALID_INPUT")
    void rejectsStringVersion() {
        ObjectNode node = Jcs.objectNode();
        node.put("schema_version", "1");
        assertInvalidInput(node);
    }

    @Test
    @DisplayName("显式小数版本 → 400 INVALID_INPUT")
    void rejectsFractionalVersion() {
        ObjectNode node = Jcs.objectNode();
        node.put("schema_version", 1.5);
        assertInvalidInput(node);
    }

    @Test
    @DisplayName("顶层数组 → 400 INVALID_INPUT（不能作为带版本的摘要）")
    void rejectsNonObject() {
        assertInvalidInput(Jcs.arrayNode());
    }

    private void assertInvalidInput(com.fasterxml.jackson.databind.JsonNode node) {
        ApiException ex = assertThrows(ApiException.class,
                () -> IdempotencyService.ensureSchemaVersion(node));
        assertEquals(ErrorCode.INVALID_INPUT, ex.getCode());
    }
}

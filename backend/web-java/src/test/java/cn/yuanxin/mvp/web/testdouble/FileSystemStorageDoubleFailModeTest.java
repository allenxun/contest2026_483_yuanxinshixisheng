package cn.yuanxin.mvp.web.testdouble;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SC-C-05 存储失败注入开关的语法与按 purpose 选择性（纯单元，不依赖 PG/HTTP）：
 * 默认关闭、全局 fail-put、按 purpose fail-put、非法取值装配期 fail fast；
 * get/exists/delete 不受 put 注入影响。
 *
 * <p>使用模块内 {@code target/} 目录（不用 /tmp）。</p>
 */
class FileSystemStorageDoubleFailModeTest {

    private static final byte[] BYTES = "img-bytes".getBytes(StandardCharsets.UTF_8);

    /** 每个用例独立根目录；位于模块 target/ 下，不写 /tmp。 */
    private static Path root() {
        return Path.of("target", "storage-unit", UUID.randomUUID().toString());
    }

    private static void put(FileSystemStorageDouble storage, String key) {
        storage.put(key, new ByteArrayInputStream(BYTES), BYTES.length, "image/png");
    }

    @Test
    @DisplayName("默认构造 = none：不注入，写入成功且可读")
    void defaultIsNone() throws IOException {
        FileSystemStorageDouble storage = new FileSystemStorageDouble(root().toString());
        assertFalse(storage.failAllPuts());
        assertEquals(Set.of(), storage.failPurposes());
        put(storage, "test/assessment_source/a");
        assertTrue(storage.exists("test/assessment_source/a"));
        assertArrayEquals(BYTES, storage.get("test/assessment_source/a"));
    }

    @Test
    @DisplayName("fail-put：所有 purpose 写入抛 UncheckedIOException；读/存在性不受影响")
    void failPutAllPurposes() {
        FileSystemStorageDouble storage =
                new FileSystemStorageDouble(root().toString(), "fail-put");
        assertTrue(storage.failAllPuts());
        assertThrows(UncheckedIOException.class, () -> put(storage, "test/assessment_source/a"));
        assertThrows(UncheckedIOException.class, () -> put(storage, "test/grant_face/b"));
        assertFalse(storage.exists("test/assessment_source/a"));
        storage.delete("test/assessment_source/a"); // 不抛：删除未受注入影响
    }

    @Test
    @DisplayName("fail-put:<purpose>：仅列出的 purpose 失败，其它 purpose 正常写入")
    void failPutPerPurpose() throws IOException {
        FileSystemStorageDouble storage =
                new FileSystemStorageDouble(root().toString(), "fail-put:assessment_source");
        assertEquals(Set.of("assessment_source"), storage.failPurposes());
        assertThrows(UncheckedIOException.class, () -> put(storage, "test/assessment_source/a"));
        // 关键隔离：grant_face（M1-A01）不受 assessment_source 失败影响
        put(storage, "test/grant_face/b");
        assertTrue(storage.exists("test/grant_face/b"));
        assertArrayEquals(BYTES, storage.get("test/grant_face/b"));
    }

    @Test
    @DisplayName("fail-put:<p1>,<p2> 多项；大小写/空白容错")
    void failPutMultiplePurposes() {
        FileSystemStorageDouble storage = new FileSystemStorageDouble(root().toString(),
                " FAIL-PUT:Grant_Face , assessment_result ");
        assertEquals(Set.of("grant_face", "assessment_result"), storage.failPurposes());
        assertThrows(UncheckedIOException.class, () -> put(storage, "test/grant_face/a"));
        assertThrows(UncheckedIOException.class, () -> put(storage, "test/assessment_result/b"));
        put(storage, "test/assessment_source/c"); // 未列出 → 正常
        assertTrue(storage.exists("test/assessment_source/c"));
    }

    @Test
    @DisplayName("非法取值（未知值/空 purpose/未知 purpose）→ 构造期 IllegalArgumentException（fail fast）")
    void illegalValuesFailFast() {
        assertThrows(IllegalArgumentException.class,
                () -> new FileSystemStorageDouble(root().toString(), "bogus"));
        assertThrows(IllegalArgumentException.class,
                () -> new FileSystemStorageDouble(root().toString(), "fail-put:"));
        assertThrows(IllegalArgumentException.class,
                () -> new FileSystemStorageDouble(root().toString(), "fail-put:not_a_purpose"));
    }
}

package cn.yuanxin.mvp.web.assessments;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SC-C-05 恢复与持久：开关缺省（{@code none}，即不设 env）时同一上传流程正常
 * 完成，对象真实落盘；用新的 {@link FileSystemStorageDouble} 实例指向同一根目录
 * 仍可读回（模拟"重启后仍可读"），证明注入是受控且可恢复的。
 */
@TestPropertySource(properties = {
        "app.storage.dev-dir=target/storage-it/recovery"
})
class StorageFailModeRecoveryIT extends AssessmentTestSupport {

    @Autowired
    StoragePort storagePort;

    @Autowired
    AppProperties appProperties;

    @Test
    @DisplayName("SC-C-05 复位：默认 none → A01 正常 202，对象落盘，新替身实例（重启）仍可读")
    void defaultModeSavesAndRestartCanRead() throws Exception {
        FileSystemStorageDouble storage = assertInstanceOf(FileSystemStorageDouble.class, storagePort);
        assertFalse(storage.failAllPuts(), "未设 env 时必须默认关闭注入");
        assertTrue(storage.failPurposes().isEmpty());

        GimbalFixture gimbal = createGimbal();
        String key = "d-a01-recovery-" + UUID.randomUUID();
        MvcResult r = postA01(gimbal.token(), key);
        assertEquals(202, r.getResponse().getStatus(), r.getResponse().getContentAsString());

        UUID t13 = t13IdForGimbalKey(gimbal.gimbalId(), key);
        Integer available = jdbc.queryForObject("SELECT count(*) FROM media_objects"
                + " WHERE request_id = ? AND state = 'available'", Integer.class, t13);
        assertEquals(3, available, "三个视角均应 available");

        UUID taskId = UUID.fromString(JSON.readTree(r.getResponse().getContentAsString())
                .path("data").path("taskId").asText());
        String frontMediaId = frontMediaIdOf(taskId);
        String objectKey = jdbc.queryForObject(
                "SELECT object_key FROM media_objects WHERE id = ?::uuid", String.class, frontMediaId);

        Path root = Path.of(appProperties.storage().devDir()).toAbsolutePath().normalize();
        Path file = root.resolve(objectKey);
        assertTrue(Files.exists(file), "对象必须真实落盘: " + file);
        assertArrayEquals(png(1), Files.readAllBytes(file));

        // "重启"：新替身实例指向同一根目录，仍可读回同一对象
        FileSystemStorageDouble restarted =
                new FileSystemStorageDouble(appProperties.storage().devDir());
        assertTrue(restarted.exists(objectKey));
        assertArrayEquals(png(1), restarted.get(objectKey));
    }

    private String frontMediaIdOf(UUID taskId) throws Exception {
        JsonNode versions = JSON.readTree(jdbc.queryForObject(
                "SELECT photo_versions::text FROM skin_assessments WHERE id = ?", String.class, taskId))
                .path("versions");
        for (JsonNode version : versions) {
            if (version.path("version").asLong(-1) == 1L) {
                return version.path("images").path("front").asText();
            }
        }
        throw new AssertionError("version 1 not found for task " + taskId);
    }
}

package cn.yuanxin.mvp.web.state;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * {@link L3Cleanup} 判别测试（不需 Spring/Redis）：证明<b>只要任一步骤异常（或 SCAN 残留/无法复核），
 * 清理就必须失败</b>——尤其是"删除抛异常但键其实已不存在（SCAN=0）"这一 IMPORTANT 4 未闭合场景。
 */
class L3CleanupTest {

    @Test
    @DisplayName("Redis 删除抛异常但 SCAN=0 ⇒ 仍必须失败（不能只打印却 PASS）")
    void deleteThrowsButScanZeroStillFails() {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        IllegalStateException thrown = runExpectingFailure(
                () -> {
                    throw new RedisConnectionFailureException(
                            "Unable to connect to redis://user:secret@10.0.0.9:6379/5");
                },
                () -> 0,
                () -> new int[]{1, 1},
                buffer);

        assertThat(thrown).hasMessageContaining("cleanup incomplete");
        assertThat(thrown.getSuppressed()).as("原始清理异常须以 suppressed 保留").isNotEmpty();
        String out = buffer.toString(StandardCharsets.UTF_8);
        assertThat(out).contains("redisLeftover=0")
                .contains("cleanup-incomplete-suppressed=RedisConnectionFailureException");
        assertThat(out).doesNotContain("10.0.0.9").doesNotContain("6379").doesNotContain("secret");
    }

    @Test
    @DisplayName("SCAN 复核到残留键 >0 ⇒ 失败")
    void scanLeftoverFails() {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        IllegalStateException thrown = runExpectingFailure(
                () -> { },
                () -> 3,
                () -> new int[]{0, 0},
                buffer);
        assertThat(thrown).hasMessageContaining("cleanup incomplete");
        assertThat(buffer.toString(StandardCharsets.UTF_8)).contains("redisLeftover=3");
    }

    @Test
    @DisplayName("SCAN 自身抛异常（无法复核）⇒ 失败，输出 unverified")
    void scanThrowsFails() {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        IllegalStateException thrown = runExpectingFailure(
                () -> { },
                () -> {
                    throw new QueryTimeoutException("timeout host=10.0.0.9:6379");
                },
                () -> new int[]{0, 0},
                buffer);
        assertThat(thrown).hasMessageContaining("cleanup incomplete");
        String out = buffer.toString(StandardCharsets.UTF_8);
        assertThat(out).contains("redisLeftover=unverified")
                .contains("cleanup-incomplete-suppressed=QueryTimeoutException");
        assertThat(out).doesNotContain("10.0.0.9").doesNotContain("6379");
    }

    @Test
    @DisplayName("DB 删除抛异常 ⇒ 失败（并以 suppressed 保留），输出只含类名")
    void dbThrowsFails() {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        IllegalStateException thrown = runExpectingFailure(
                () -> { },
                () -> 0,
                () -> {
                    throw new IllegalStateException("db host=10.0.0.9 password=secret");
                },
                buffer);
        assertThat(thrown).hasMessageContaining("cleanup incomplete");
        assertThat(thrown.getSuppressed()).isNotEmpty();
        String out = buffer.toString(StandardCharsets.UTF_8);
        assertThat(out).contains("db-cleanup-error exception=IllegalStateException");
        assertThat(out).doesNotContain("10.0.0.9").doesNotContain("password").doesNotContain("secret");
    }

    @Test
    @DisplayName("全部成功 ⇒ 不抛，输出计数")
    void allOkPasses() {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        L3Cleanup.run(() -> { }, () -> 0, () -> new int[]{2, 1},
                new PrintStream(buffer, true, StandardCharsets.UTF_8));
        String out = buffer.toString(StandardCharsets.UTF_8);
        assertThat(out).contains("redisLeftover=0")
                .contains("destinationsDeleted=2")
                .contains("accountsDeleted=1")
                .doesNotContain("cleanup-incomplete-suppressed");
    }

    @Test
    @DisplayName("DB 删除行数为 0 也如实输出且不失败")
    void dbZeroRowsReportsAndPasses() {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        L3Cleanup.run(() -> { }, () -> 0, () -> new int[]{0, 0},
                new PrintStream(buffer, true, StandardCharsets.UTF_8));
        String out = buffer.toString(StandardCharsets.UTF_8);
        assertThat(out).contains("destinationsDeleted=0").contains("accountsDeleted=0");
        assertThat(out).doesNotContain("cleanup-incomplete-suppressed");
    }

    @Test
    @DisplayName("多个步骤同时失败 ⇒ suppressed 累积（至少 1 个）")
    void suppressedAccumulates() {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        IllegalStateException thrown = runExpectingFailure(
                () -> {
                    throw new RedisConnectionFailureException("connect fail");
                },
                () -> 0,
                () -> {
                    throw new IllegalStateException("db fail");
                },
                buffer);
        assertThat(thrown.getSuppressed()).isNotEmpty();
    }

    // ---------- helpers ----------

    private static IllegalStateException runExpectingFailure(
            L3Cleanup.RedisDelete delete, L3Cleanup.RedisScan scan, L3Cleanup.DbDelete db, ByteArrayOutputStream out) {
        IllegalStateException thrown = null;
        try {
            L3Cleanup.run(delete, scan, db, new PrintStream(out, true, StandardCharsets.UTF_8));
        } catch (IllegalStateException failure) {
            thrown = failure;
        }
        assertThat(thrown).as("cleanup must fail").isNotNull();
        return thrown;
    }
}

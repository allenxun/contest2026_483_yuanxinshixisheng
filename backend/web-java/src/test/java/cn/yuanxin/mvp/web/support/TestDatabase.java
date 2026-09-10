package cn.yuanxin.mvp.web.support;

import org.flywaydb.core.Flyway;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.UUID;

/**
 * 会话级共享的临时测试数据库（decisions.md 测试隔离约定）。
 * 首次使用时创建 mvp_a_test_j_&lt;uuid&gt;（连 postgres 管理库建库），跑
 * Flyway V1+V2，JVM shutdown hook 强制删库——多个 @SpringBootTest
 * 类共享同一库、同一缓存上下文，控制总时长。
 * 连接参数与 FlywayMigrationIntegrationTest 一致（MVP_A_PG_* env 覆盖）。
 */
public final class TestDatabase {

    private static final String ADMIN_JDBC = env("MVP_A_PG_JDBC",
            "jdbc:postgresql://127.0.0.1:55432/postgres");
    private static final String ADMIN_USER = env("MVP_A_PG_USER", "postgres");
    private static final String ADMIN_PASSWORD = env("MVP_A_PG_PASSWORD", "mvp_a_local");

    private static final String DB_NAME =
            "mvp_a_test_j_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    private static final String URL =
            ADMIN_JDBC.substring(0, ADMIN_JDBC.lastIndexOf('/') + 1) + DB_NAME;

    private static boolean initialized;

    private TestDatabase() {
    }

    public static synchronized String url() {
        init();
        return URL;
    }

    public static String user() {
        return ADMIN_USER;
    }

    public static String password() {
        return ADMIN_PASSWORD;
    }

    private static void init() {
        if (initialized) {
            return;
        }
        try (Connection admin = DriverManager.getConnection(ADMIN_JDBC, ADMIN_USER, ADMIN_PASSWORD);
             Statement st = admin.createStatement()) {
            st.execute("CREATE DATABASE " + DB_NAME);
        } catch (Exception e) {
            throw new IllegalStateException("cannot create ephemeral test database", e);
        }
        Flyway.configure().dataSource(URL, ADMIN_USER, ADMIN_PASSWORD).load().migrate();
        initialized = true;
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try (Connection admin = DriverManager.getConnection(ADMIN_JDBC, ADMIN_USER, ADMIN_PASSWORD);
                 Statement st = admin.createStatement()) {
                st.execute("DROP DATABASE IF EXISTS " + DB_NAME + " WITH (FORCE)");
            } catch (Exception ignored) {
                // 尽力而为：CI 场景容器随 worktree 消亡
            }
        }, "mvp-a-test-db-cleanup"));
    }

    private static String env(String key, String def) {
        String v = System.getenv(key);
        return (v == null || v.isBlank()) ? def : v;
    }
}

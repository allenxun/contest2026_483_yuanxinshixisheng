package cn.yuanxin.mvp.web.migration;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

/**
 * Flyway 迁移集成测试：对真实 PostgreSQL 16（隔离容器 mvp-a-pg）执行。
 * 每次运行创建独立数据库 mvp_a_test_&lt;random&gt;（decisions.md 测试隔离约定），@AfterAll 删除。
 * 覆盖：14 表存在、双占用拒绝、记录来源去重、T13 唯一键、status CHECK、
 * current_photo_version&gt;0 CHECK、循环外键（正/反例）、重复迁移幂等。
 */
class FlywayMigrationIntegrationTest {

    private static final String ADMIN_JDBC = env("MVP_A_PG_JDBC", "jdbc:postgresql://127.0.0.1:55432/postgres");
    private static final String ADMIN_USER = env("MVP_A_PG_USER", "postgres");
    private static final String ADMIN_PASSWORD = env("MVP_A_PG_PASSWORD", "mvp_a_local");

    private static final String TEST_DB =
            "mvp_a_test_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    private static final String TEST_JDBC =
            ADMIN_JDBC.substring(0, ADMIN_JDBC.lastIndexOf('/') + 1) + TEST_DB;

    private static final List<String> EXPECTED_TABLES = List.of(
            "accounts", "members", "member_access_grants", "gimbals", "microcrystals",
            "skin_assessments", "care_plans", "care_executions", "care_records",
            "notification_destinations", "notifications", "media_objects",
            "async_jobs", "idempotency_requests");

    private static Connection admin;
    private static Connection conn;
    private static int seq;

    private static String env(String key, String def) {
        String v = System.getenv(key);
        return (v == null || v.isBlank()) ? def : v;
    }

    @BeforeAll
    static void createDatabaseAndMigrate() throws Exception {
        admin = DriverManager.getConnection(ADMIN_JDBC, ADMIN_USER, ADMIN_PASSWORD);
        admin.setAutoCommit(true);
        try (Statement st = admin.createStatement()) {
            st.execute("CREATE DATABASE " + TEST_DB);
        }
        conn = DriverManager.getConnection(TEST_JDBC, ADMIN_USER, ADMIN_PASSWORD);
        conn.setAutoCommit(true);
        var stats = migrate();
        assertEquals(2, stats, "V1+V2 两个迁移应全部执行");
    }

    @AfterAll
    static void dropDatabase() throws Exception {
        if (conn != null) conn.close();
        if (admin != null) {
            try (Statement st = admin.createStatement()) {
                st.execute("DROP DATABASE IF EXISTS " + TEST_DB + " WITH (FORCE)");
            }
            admin.close();
        }
    }

    /** 运行 Flyway migrate，返回实际执行的迁移数。 */
    private static int migrate() {
        Flyway flyway = Flyway.configure()
                .dataSource(TEST_JDBC, ADMIN_USER, ADMIN_PASSWORD)
                .load();
        return flyway.migrate().migrationsExecuted;
    }

    // ---------- fixtures ----------

    private record Fixture(String accountId, String memberId, String gimbalId,
                           String microId, String assessmentId, String planId) {}

    private static String uuid() {
        return UUID.randomUUID().toString();
    }

    private static void insert(String sql, Object... params) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            for (int i = 0; i < params.length; i++) ps.setObject(i + 1, coerce(params[i]));
            ps.executeUpdate();
        }
    }

    private static final java.util.regex.Pattern UUID_RE = java.util.regex.Pattern.compile(
            "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");

    /** PG16 不把 varchar 参数隐式转 uuid：测试里的 uuid 字符串统一转 java.util.UUID。 */
    private static Object coerce(Object p) {
        if (p instanceof String s && UUID_RE.matcher(s).matches()) return UUID.fromString(s);
        return p;
    }

    /** 断言插入失败且错误信息包含指定约束/索引名。 */
    private static void assertRejected(String constraintName, String sql, Object... params) {
        try {
            insert(sql, params);
            fail("expected violation of " + constraintName);
        } catch (SQLException e) {
            assertNotNull(e.getMessage(), "constraint " + constraintName);
            assertTrue(e.getMessage().contains(constraintName),
                    "expected error about " + constraintName + " but got: " + e.getMessage());
        }
    }

    private static String newIdempotencyRequest() throws SQLException {
        String id = uuid();
        insert("INSERT INTO idempotency_requests"
                        + " (id, principal_type, principal_id, operation, idempotency_key, payload_hash)"
                        + " VALUES (?, 'app_account', ?, ?, ?, 'sha256:placeholder')",
                id, "seed-principal:" + (++seq), "seed:op", "seed:key:" + seq);
        return id;
    }

    /** 建立 accounts/members/gimbals/microcrystals/skin_assessments/care_plans 各一行。 */
    private static Fixture newFixture() throws SQLException {
        int n = ++seq;
        String a = uuid(), m = uuid(), g = uuid(), mc = uuid(), s = uuid(), p = uuid();
        insert("INSERT INTO accounts (id, login_provider, login_subject) VALUES (?, 'test-provider', ?)",
                a, "subject-" + n);
        insert("INSERT INTO members (id) VALUES (?)", m);
        insert("INSERT INTO gimbals (id, serial_no, auth_subject_ref) VALUES (?, ?, ?)",
                g, "SN-G-" + n, "authref-" + n);
        insert("INSERT INTO microcrystals (id, serial_no) VALUES (?, ?)", mc, "SN-M-" + n);
        insert("INSERT INTO skin_assessments (id, gimbal_id, member_id, source_request_id) VALUES (?, ?, ?, ?)",
                s, g, m, newIdempotencyRequest());
        insert("INSERT INTO care_plans (id, assessment_id, member_id) VALUES (?, ?, ?)", p, s, m);
        return new Fixture(a, m, g, mc, s, p);
    }

    private static String newExecution(Fixture f, String controllerGimbalId) throws SQLException {
        String e = uuid();
        if (controllerGimbalId == null) {
            insert("INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                            + " controller_type, controller_account_id, controller_installation_id,"
                            + " assessment_id_at_start, source_request_id)"
                            + " VALUES (?, ?, ?, ?, 'app', ?, 'inst-1', ?, ?)",
                    e, f.planId(), f.memberId(), f.microId(), f.accountId(), f.assessmentId(),
                    newIdempotencyRequest());
        } else {
            insert("INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                            + " controller_type, controller_gimbal_id,"
                            + " assessment_id_at_start, source_request_id)"
                            + " VALUES (?, ?, ?, ?, 'gimbal', ?, ?, ?)",
                    e, f.planId(), f.memberId(), f.microId(), controllerGimbalId,
                    f.assessmentId(), newIdempotencyRequest());
        }
        return e;
    }

    // ---------- assertions ----------

    @Test
    @DisplayName("V1/V2 后 14 张业务表全部存在")
    void all14TablesExist() throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT count(*) FROM information_schema.tables"
                        + " WHERE table_schema = 'public' AND table_name = ANY(?)")) {
            java.sql.Array arr = conn.createArrayOf("text", EXPECTED_TABLES.toArray());
            ps.setArray(1, arr);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                assertEquals(14, rs.getInt(1), "14 表应全部由迁移创建");
            }
        }
    }

    @Test
    @DisplayName("(a) 同一微晶两个未收尾执行被 uq_execution_open_microcrystal 拒绝；收尾后可再开")
    void doubleOccupancyRejected() throws SQLException {
        Fixture f = newFixture();
        String e1 = newExecution(f, null);
        // 第二个未收尾执行：microcrystal_id 相同（合法控制端形状——归属 CHECK 由 (g) 单独覆盖）
        try {
            insert("INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                            + " controller_type, controller_account_id, controller_installation_id,"
                            + " assessment_id_at_start, source_request_id)"
                            + " VALUES (?, ?, ?, ?, 'app', ?, 'inst-2', ?, ?)",
                    uuid(), f.planId(), f.memberId(), f.microId(), f.accountId(),
                    f.assessmentId(), newIdempotencyRequest());
            fail("expected uq_execution_open_microcrystal violation");
        } catch (SQLException e) {
            assertTrue(e.getMessage().contains("uq_execution_open_microcrystal"), e.getMessage());
        }
        // 收尾后占用释放
        insert("UPDATE care_executions SET status = 'closed', closed_at = now() WHERE id = ?", e1);
        newExecution(f, null); // 不应抛错
    }

    private static String newMicro() throws SQLException {
        String mc = uuid();
        insert("INSERT INTO microcrystals (id, serial_no) VALUES (?, ?)", mc, "SN-M-X" + (++seq));
        return mc;
    }

    @Test
    @DisplayName("(a+) 同一云台两个未收尾控制执行被 uq_execution_open_gimbal 拒绝")
    void doubleGimbalControlRejected() throws SQLException {
        Fixture f = newFixture();
        newExecution(f, f.gimbalId());
        assertRejected("uq_execution_open_gimbal",
                "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                        + " controller_type, controller_gimbal_id, assessment_id_at_start, source_request_id)"
                        + " VALUES (?, ?, ?, ?, 'gimbal', ?, ?, ?)",
                uuid(), f.planId(), f.memberId(), newMicro(), f.gimbalId(), f.assessmentId(),
                newIdempotencyRequest());
    }

    @Test
    @DisplayName("(b) care_records 重复 (execution_id, source_epoch, source_seq) 被拒绝")
    void duplicateRecordSourceRejected() throws SQLException {
        Fixture f = newFixture();
        String e = newExecution(f, null);
        String rec = "INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id,"
                + " microcrystal_id, count_delta, source_epoch, source_seq, payload_hash, payload)"
                + " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 'sha256:x', '{\"schema_version\":1}')";
        insert(rec, uuid(), e, "client-1", f.planId(), f.memberId(), f.microId(), "ep1", 1L);
        assertRejected("uq_record_source", rec, uuid(), e, "client-2", f.planId(), f.memberId(),
                f.microId(), "ep1", 1L);
        assertRejected("uq_record_client", rec, uuid(), e, "client-1", f.planId(), f.memberId(),
                f.microId(), "ep1", 2L);
        assertRejected("ck_record_count_delta",
                "INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id,"
                        + " microcrystal_id, count_delta, source_epoch, source_seq, payload_hash, payload)"
                        + " VALUES (?, ?, ?, ?, ?, ?, 0, ?, 9, 'sha256:x', '{\"schema_version\":1}')",
                uuid(), e, "client-3", f.planId(), f.memberId(), f.microId(), "ep1");
    }

    @Test
    @DisplayName("(g) care_executions 控制端归属 CHECK：app 必须 account+installation、gimbal 必须只带 gimbal")
    void controllerOwnershipCheck() throws SQLException {
        Fixture f = newFixture();
        // app 但缺 account → 拒绝（oracle B3 的非法形状）
        assertRejected("ck_execution_controller_ownership",
                "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                        + " controller_type, assessment_id_at_start, source_request_id)"
                        + " VALUES (?, ?, ?, ?, 'app', ?, ?)",
                uuid(), f.planId(), f.memberId(), f.microId(), f.assessmentId(),
                newIdempotencyRequest());
        // app 有 account 缺 installation → 拒绝
        assertRejected("ck_execution_controller_ownership",
                "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                        + " controller_type, controller_account_id, assessment_id_at_start,"
                        + " source_request_id) VALUES (?, ?, ?, ?, 'app', ?, ?, ?)",
                uuid(), f.planId(), f.memberId(), f.microId(), f.accountId(),
                f.assessmentId(), newIdempotencyRequest());
        // gimbal 混入 account → 拒绝
        assertRejected("ck_execution_controller_ownership",
                "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                        + " controller_type, controller_account_id, controller_gimbal_id,"
                        + " assessment_id_at_start, source_request_id)"
                        + " VALUES (?, ?, ?, ?, 'gimbal', ?, ?, ?, ?)",
                uuid(), f.planId(), f.memberId(), f.microId(), f.accountId(), f.gimbalId(),
                f.assessmentId(), newIdempotencyRequest());
        newExecution(f, null);        // 合法 app 形状
        newExecutionGimbal(f);        // 合法 gimbal 形状（另一微晶避免占用冲突）
    }

    private static void newExecutionGimbal(Fixture f) throws SQLException {
        insert("INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                        + " controller_type, controller_gimbal_id, assessment_id_at_start,"
                        + " source_request_id) VALUES (?, ?, ?, ?, 'gimbal', ?, ?, ?)",
                uuid(), f.planId(), f.memberId(), newMicro(), f.gimbalId(),
                f.assessmentId(), newIdempotencyRequest());
    }

    @Test
    @DisplayName("(h) notification_destinations active 必须有非空 registration；registration 有值须带 schema_version")
    void destinationRegistrationChecks() throws SQLException {
        Fixture f = newFixture();
        assertRejected("ck_destination_active_fields",
                "INSERT INTO notification_destinations (id, installation_id, account_id,"
                        + " status, session_ref) VALUES (?, 'inst-ck-1', ?, 'active', 'sess-1')",
                uuid(), f.accountId());
        assertRejected("ck_destination_active_fields",
                "INSERT INTO notification_destinations (id, installation_id, account_id,"
                        + " status, session_ref, registration) VALUES (?, 'inst-ck-2', ?, 'active',"
                        + " 'sess-1', '{}'::jsonb)",
                uuid(), f.accountId());
        assertRejected("ck_destination_registration_schema",
                "INSERT INTO notification_destinations (id, installation_id, account_id,"
                        + " status, session_ref, registration) VALUES (?, 'inst-ck-3', ?, 'active',"
                        + " 'sess-1', '{\"token\":\"x\"}'::jsonb)",
                uuid(), f.accountId());
        // 合法：active + 非空带版本
        insert("INSERT INTO notification_destinations (id, installation_id, account_id,"
                        + " status, session_ref, registration) VALUES (?, 'inst-ck-4', ?, 'active',"
                        + " 'sess-1', '{\"schema_version\":1,\"token\":\"x\"}'::jsonb)",
                uuid(), f.accountId());
        // 合法：inactive 可空 registration（默认 '{}'）
        insert("INSERT INTO notification_destinations (id, installation_id, status)"
                        + " VALUES (?, 'inst-ck-5', 'invalid')",
                uuid());
    }

    @Test
    @DisplayName("(i) JSONB schema_version CHECK：媒体 storage_metadata 非空必须带版本；pending 空占位合法")
    void mediaStorageMetadataSchema() throws SQLException {
        assertRejected("ck_media_storage_metadata_schema",
                "INSERT INTO media_objects (id, bucket, object_key, purpose, state, storage_metadata)"
                        + " VALUES (?, 'b', 'dev/x/1', 'assessment_source', 'pending',"
                        + " '{\"upgraded_by\":\"y\"}'::jsonb)",
                uuid());
        // 空占位（默认 '{}'）合法
        insert("INSERT INTO media_objects (id, bucket, object_key, purpose, state)"
                + " VALUES (?, 'b', 'dev/x/2', 'assessment_source', 'pending')", uuid());
    }

    @Test
    @DisplayName("(c) idempotency_requests 重复 (principal_type, principal_id, operation, idempotency_key) 被拒绝")
    void duplicateIdempotencyKeyRejected() throws SQLException {
        String ins = "INSERT INTO idempotency_requests (id, principal_type, principal_id, operation,"
                + " idempotency_key, payload_hash) VALUES (?, 'app_account', 'acct:inst', 'op-x', ?, 'sha256:a')";
        insert(ins, uuid(), "key-1");
        assertRejected("uq_idem_principal", ins, uuid(), "key-1");
    }

    @Test
    @DisplayName("(d) skin_assessments 非法 status 被 CHECK 拒绝")
    void invalidAssessmentStatusRejected() throws SQLException {
        Fixture f = newFixture();
        assertRejected("ck_assessment_status",
                "INSERT INTO skin_assessments (id, gimbal_id, member_id, status, source_request_id)"
                        + " VALUES (?, ?, ?, 'bogus', ?)",
                uuid(), f.gimbalId(), f.memberId(), newIdempotencyRequest());
    }

    @Test
    @DisplayName("(e) current_photo_version > 0 CHECK 生效")
    void currentPhotoVersionCheck() throws SQLException {
        Fixture f = newFixture();
        assertRejected("ck_assessment_current_photo_version",
                "INSERT INTO skin_assessments (id, gimbal_id, member_id, current_photo_version,"
                        + " source_request_id) VALUES (?, ?, ?, 0, ?)",
                uuid(), f.gimbalId(), f.memberId(), newIdempotencyRequest());
        insert("INSERT INTO skin_assessments (id, gimbal_id, member_id, current_photo_version,"
                        + " source_request_id) VALUES (?, ?, ?, 1, ?)",
                uuid(), f.gimbalId(), f.memberId(), newIdempotencyRequest());
    }

    @Test
    @DisplayName("(f) 循环外键：指针可指向本云台任务，跨云台/不存在的行被拒绝")
    void circularForeignKeyWorks() throws SQLException {
        Fixture mine = newFixture();
        Fixture other = newFixture();
        // 先插任务再更新指针（任务已在 newFixture 中插入）
        insert("UPDATE gimbals SET current_assessment_id = ?, current_assessment_revision = 1 WHERE id = ?",
                mine.assessmentId(), mine.gimbalId());
        assertRejected("fk_gimbal_current_assessment",
                "UPDATE gimbals SET current_assessment_id = ? WHERE id = ?",
                other.assessmentId(), mine.gimbalId());
        assertRejected("fk_gimbal_current_assessment",
                "UPDATE gimbals SET current_assessment_id = ? WHERE id = ?",
                uuid(), mine.gimbalId());
        // members.created_from_assessment_id 循环外键
        insert("UPDATE members SET created_from_assessment_id = ? WHERE id = ?",
                mine.assessmentId(), mine.memberId());
        assertRejected("fk_member_created_from_assessment",
                "UPDATE members SET created_from_assessment_id = ? WHERE id = ?",
                uuid(), mine.memberId());
    }

    @Test
    @DisplayName("(g) 重复运行 Flyway migrate = 无操作且成功")
    void reMigrateIsNoop() {
        assertEquals(0, migrate(), "重复迁移不应执行任何迁移");
    }
}

package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.time.Instant;
import java.util.Arrays;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.CAPTURED_AT;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.PNG;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.capture;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M4-A03 / M4-A04 真实 PG 并发准入：两个部分唯一索引（微晶 / 云台未收尾）
 * 原子裁决占用；A04 同 expectedRevision 并发只放行一个。
 */
class CareAdmissionConcurrencyIT extends AbstractWebIT {

    private static final String CAPABILITIES = "{\"schema_version\":1,\"revision\":\"1\"}";

    private static final String LATEST_OBS = "{\"schema_version\":1,\"epoch\":\"epoch-1\","
            + "\"seq\":\"2\",\"state\":\"paused\",\"occurred_at\":\"2026-09-10T04:00:00Z\","
            + "\"verification_revision\":\"1\",\"continuity_valid\":false,"
            + "\"continuity_invalidated\":true}";

    private static final String SNAPSHOT = "{\"schema_version\":1,"
            + "\"plan_id\":\"00000000-0000-0000-0000-000000000001\",\"target_count\":\"5\","
            + "\"summary\":null,\"execution_params\":{\"title\":\"快照方案\"},"
            + "\"verification\":{\"purpose\":\"admission\"}}";

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private MvcResult[] concurrent(Callable<MvcResult> first, Callable<MvcResult> second)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<MvcResult> f1 = pool.submit(() -> {
                start.await();
                return first.call();
            });
            Future<MvcResult> f2 = pool.submit(() -> {
                start.await();
                return second.call();
            });
            start.countDown();
            return new MvcResult[]{f1.get(60, TimeUnit.SECONDS), f2.get(60, TimeUnit.SECONDS)};
        } finally {
            pool.shutdownNow();
        }
    }

    private static int[] statuses(MvcResult[] results) {
        return Arrays.stream(results).mapToInt(r -> r.getResponse().getStatus()).sorted().toArray();
    }

    private static MvcResult conflict(MvcResult[] results) {
        return results[0].getResponse().getStatus() == 409 ? results[0] : results[1];
    }

    private static MvcResult success(MvcResult[] results) {
        return results[0].getResponse().getStatus() == 201 ? results[0] : results[1];
    }

    private static String code(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error").path("code").asText();
    }

    private static String reason(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error").path("details")
                .path("reason").asText();
    }

    private String metadata(UUID microcrystalId, String proof, UUID planId) {
        return CareAdmissionTestSupport.admissionMetadata(microcrystalId, proof, planId, null, null,
                capture("cap-" + UUID.randomUUID(), CAPTURED_AT, "cc", "admission"), "consent");
    }

    @Test
    @DisplayName("A03 并发同微晶双 APP：恰一个 201 一个 409 DEVICE_OCCUPIED，T07 仅 1 行")
    void concurrentSameMicrocrystal() throws Exception {
        UUID memberId = fx.seedMember();
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-conc-a");
        LoginResult b = loginAppWithInstallation(newPhone(), "inst-conc-b");
        fx.seedGrant(UUID.fromString(a.accountId()), memberId, "active");
        fx.seedGrant(UUID.fromString(b.accountId()), memberId, "active");
        UUID gimbalId = fx.seedGimbal("conc-mic-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID microcrystal = fx.seedMicrocrystal(CAPABILITIES);

        MvcResult[] results = concurrent(
                () -> CareAdmissionTestSupport.admit(mockMvc, a.accessToken(),
                        CareAdmissionTestSupport.newKey(), metadata(microcrystal, "pa", planId), PNG),
                () -> CareAdmissionTestSupport.admit(mockMvc, b.accessToken(),
                        CareAdmissionTestSupport.newKey(), metadata(microcrystal, "pb", planId), PNG));

        assertArrayEqualsInt(new int[]{201, 409}, statuses(results));
        assertEquals("DEVICE_OCCUPIED", code(conflict(results)));
        assertEquals(1, jdbc.queryForObject(
                "SELECT count(*) FROM care_executions WHERE microcrystal_id = ?", Integer.class,
                microcrystal));
        assertTrue(success(results).getResponse().getStatus() == 201);
    }

    @Test
    @DisplayName("A03 并发同云台双微晶：恰一个 201 一个 409（uq_execution_open_gimbal）")
    void concurrentSameGimbal() throws Exception {
        UUID gimbalId = fx.seedGimbal("conc-gim-login-" + UUID.randomUUID(), 1);
        String token = fx.loginGimbal(mockMvc, gimbalId);
        UUID memberId = fx.seedMember();
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 5, 0, 0, null);
        fx.pointGimbalAtAssessment(gimbalId, assessment);
        UUID microA = fx.seedMicrocrystal(CAPABILITIES);
        UUID microB = fx.seedMicrocrystal(CAPABILITIES);

        Callable<MvcResult> first = () -> CareAdmissionTestSupport.admit(mockMvc, token,
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(microA, "pa", null, assessment, "1",
                        capture("ca", CAPTURED_AT, "cc", "admission"), "consent"), PNG);
        Callable<MvcResult> second = () -> CareAdmissionTestSupport.admit(mockMvc, token,
                CareAdmissionTestSupport.newKey(),
                CareAdmissionTestSupport.admissionMetadata(microB, "pb", null, assessment, "1",
                        capture("cb", CAPTURED_AT, "cc", "admission"), "consent"), PNG);
        MvcResult[] results = concurrent(first, second);

        assertArrayEqualsInt(new int[]{201, 409}, statuses(results));
        assertEquals("DEVICE_OCCUPIED", code(conflict(results)));
        assertEquals(1, jdbc.queryForObject(
                "SELECT count(*) FROM care_executions WHERE controller_gimbal_id = ?", Integer.class,
                gimbalId));
    }

    @Test
    @DisplayName("A03 已占用微晶 409（含跨端）；仅 closed_at 释放占用")
    void occupancyReleaseOnlyByClosed() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-occ");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("occ-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);

        // 同微晶已有未收尾 stopped 执行（closed_at NULL）→ 拒绝
        UUID occupied = fx.seedMicrocrystal(CAPABILITIES);
        UUID openExecution = fx.execution(planId, memberId, occupied, fx.seedAssessment(gimbalId, memberId))
                .controllerApp(accountId, "inst-occ-other").status("stopped").insert();
        MvcResult rejected = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), metadata(occupied, "p", planId), PNG);
        assertEquals(409, rejected.getResponse().getStatus(), rejected.getResponse().getContentAsString());
        assertEquals("DEVICE_OCCUPIED", code(rejected));

        // SQL 收尾释放占用 → 新键可登记
        jdbc.update("UPDATE care_executions SET status='closed', closed_at=now(), updated_at=now()"
                + " WHERE id=?", openExecution);
        // 释放后同一微晶可重新登记
        MvcResult admitted = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), metadata(occupied, "p2", planId), PNG);
        assertEquals(201, admitted.getResponse().getStatus(), admitted.getResponse().getContentAsString());

        // 跨端：云台占用的微晶，APP 登记同样 409
        UUID gimbalOccupied = fx.seedMicrocrystal(CAPABILITIES);
        fx.execution(planId, memberId, gimbalOccupied, fx.seedAssessment(gimbalId, memberId))
                .controllerGimbal(gimbalId).status("admitted").insert();
        MvcResult cross = CareAdmissionTestSupport.admit(mockMvc, login.accessToken(),
                CareAdmissionTestSupport.newKey(), metadata(gimbalOccupied, "p3", planId), PNG);
        assertEquals(409, cross.getResponse().getStatus(), cross.getResponse().getContentAsString());
        assertEquals("DEVICE_OCCUPIED", code(cross));
    }

    @Test
    @DisplayName("A03 负对照：同方案两个不同微晶双 APP 并发 → 都 201")
    void concurrentDifferentMicrocrystalsBothSucceed() throws Exception {
        UUID memberId = fx.seedMember();
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-conc-na");
        LoginResult b = loginAppWithInstallation(newPhone(), "inst-conc-nb");
        fx.seedGrant(UUID.fromString(a.accountId()), memberId, "active");
        fx.seedGrant(UUID.fromString(b.accountId()), memberId, "active");
        UUID gimbalId = fx.seedGimbal("conc-neg-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID microA = fx.seedMicrocrystal(CAPABILITIES);
        UUID microB = fx.seedMicrocrystal(CAPABILITIES);

        MvcResult[] results = concurrent(
                () -> CareAdmissionTestSupport.admit(mockMvc, a.accessToken(),
                        CareAdmissionTestSupport.newKey(), metadata(microA, "pa", planId), PNG),
                () -> CareAdmissionTestSupport.admit(mockMvc, b.accessToken(),
                        CareAdmissionTestSupport.newKey(), metadata(microB, "pb", planId), PNG));

        assertArrayEqualsInt(new int[]{201, 201}, statuses(results));
    }

    @Test
    @DisplayName("A04 并发同 expectedRevision：恰一个 200（revision=2）一个 409 mismatch")
    void concurrentRevalidation() throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), "inst-conc-a04");
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("conc-a04-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID executionId = fx.execution(planId, memberId, fx.seedMicrocrystal(),
                        fx.seedAssessment(gimbalId, memberId))
                .controllerApp(accountId, "inst-conc-a04").status("paused").verificationRevision(1)
                .observation("epoch-1", 2, LATEST_OBS).planSnapshot(SNAPSHOT)
                .lastVerifiedAt(Instant.parse("2026-09-10T04:00:00Z")).insert();

        Callable<MvcResult> first = () -> CareAdmissionTestSupport.revalidate(mockMvc,
                login.accessToken(), executionId, CareAdmissionTestSupport.newKey(),
                revalidationMetadata("1"), PNG);
        Callable<MvcResult> second = () -> CareAdmissionTestSupport.revalidate(mockMvc,
                login.accessToken(), executionId, CareAdmissionTestSupport.newKey(),
                revalidationMetadata("1"), PNG);
        MvcResult[] results = concurrent(first, second);

        assertArrayEqualsInt(new int[]{200, 409}, statuses(results));
        MvcResult ok = results[0].getResponse().getStatus() == 200 ? results[0] : results[1];
        MvcResult conflict = results[0].getResponse().getStatus() == 409 ? results[0] : results[1];
        assertEquals("2", JSON.readTree(ok.getResponse().getContentAsString()).path("data")
                .path("verification").path("verificationRevision").asText());
        assertEquals("EXECUTION_NOT_RESUMABLE", code(conflict));
        assertEquals("verification_revision_mismatch", reason(conflict));
        assertEquals(2L, ((Number) jdbc.queryForObject(
                "SELECT verification_revision FROM care_executions WHERE id = ?", Long.class,
                executionId)).longValue());
    }

    private String revalidationMetadata(String expectedRevision) {
        return CareAdmissionTestSupport.revalidationMetadata(expectedRevision,
                capture("cap-" + UUID.randomUUID(), CAPTURED_AT, "cc-new", "revalidation"),
                "consent", null);
    }

    private static void assertArrayEqualsInt(int[] expected, int[] actual) {
        org.junit.jupiter.api.Assertions.assertArrayEquals(expected, actual);
    }
}

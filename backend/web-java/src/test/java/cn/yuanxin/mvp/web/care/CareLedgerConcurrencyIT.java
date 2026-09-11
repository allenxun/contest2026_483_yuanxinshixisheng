package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.closureBody;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.recordJson;
import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.syncBody;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** M4-A05/A06 真实 PG 并发：记录竞态收敛（不 500）与双收尾只放行一个。 */
class CareLedgerConcurrencyIT extends AbstractWebIT {

    private static final String CAPABILITIES = "{\"schema_version\":1,\"revision\":\"1\"}";
    private static final String T1 = "2026-09-10T04:00:01Z";

    @Autowired
    JdbcTemplate jdbc;

    private CareTestFixtures fx;

    @BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private record Ctx(LoginResult login, UUID memberId, UUID planId, UUID micro, UUID assessment) {
    }

    private Ctx newCtx(String inst) throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), inst);
        UUID accountId = UUID.fromString(login.accountId());
        UUID memberId = fx.seedMember();
        fx.seedGrant(accountId, memberId, "active");
        UUID gimbalId = fx.seedGimbal("ledger-conc-g-" + UUID.randomUUID(), 1);
        UUID assessment = fx.seedAssessment(gimbalId, memberId);
        UUID planId = fx.seedReadyPlan(assessment, memberId, 10, 0, 0, null);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);
        return new Ctx(login, memberId, planId, micro, assessment);
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

    private static String disposition(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("data")
                .path("acknowledgedRecords").get(0).path("disposition").asText();
    }

    @Test
    @DisplayName("A05 并发同记录异键：恰一次入账 K+1，另一侧 duplicate，不 500")
    void concurrentSameRecord() throws Exception {
        Ctx ctx = newCtx("inst-ledger-conc");
        UUID executionId = fx.execution(ctx.planId(), ctx.memberId(), ctx.micro(), ctx.assessment())
                .controllerApp(UUID.fromString(ctx.login().accountId()), "inst-ledger-conc")
                .status("admitted").observationEpoch("epoch-1").insert();
        String body = syncBody(null, List.of(recordJson("r1", "epoch-1", "1", "1", T1)));
        String path = "/api/v1/care-executions/" + executionId + "/observations";

        MvcResult[] results = concurrent(
                () -> CareAdmissionTestSupport.postJson(mockMvc, ctx.login().accessToken(), path,
                        "conc-a", body),
                () -> CareAdmissionTestSupport.postJson(mockMvc, ctx.login().accessToken(), path,
                        "conc-b", body));
        assertEquals(200, results[0].getResponse().getStatus(), results[0].getResponse().getContentAsString());
        assertEquals(200, results[1].getResponse().getStatus(), results[1].getResponse().getContentAsString());
        String firstDisposition = disposition(results[0]);
        String secondDisposition = disposition(results[1]);
        assertTrue((firstDisposition.equals("accepted") && secondDisposition.equals("duplicate"))
                        || (firstDisposition.equals("duplicate") && secondDisposition.equals("accepted")),
                firstDisposition + "/" + secondDisposition);
        assertEquals(1L, ((Number) jdbc.queryForObject(
                "SELECT accepted_count FROM care_executions WHERE id = ?", Long.class, executionId))
                .longValue());
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM care_records WHERE execution_id = ?",
                Integer.class, executionId));
        assertEquals(1L, ((Number) jdbc.queryForObject(
                "SELECT completed_count FROM care_plans WHERE id = ?", Long.class, ctx.planId()))
                .longValue());
    }

    @Test
    @DisplayName("A06 并发双收尾异键：恰一 200 一 409 already_closed，manifest 只写一次")
    void concurrentClosure() throws Exception {
        Ctx ctx = newCtx("inst-closure-conc");
        UUID executionId = fx.execution(ctx.planId(), ctx.memberId(), ctx.micro(), ctx.assessment())
                .controllerApp(UUID.fromString(ctx.login().accountId()), "inst-closure-conc")
                .status("stopped")
                .observation("epoch-1", 5L, "{\"schema_version\":1,\"epoch\":\"epoch-1\","
                        + "\"seq\":\"5\",\"state\":\"stopped\","
                        + "\"occurred_at\":\"2026-09-10T04:00:05Z\","
                        + "\"continuity_invalidated\":false}")
                .insert();
        fx.seedRecord(executionId, ctx.planId(), ctx.memberId(), ctx.micro(), "r1", "epoch-1", 1, 1);
        String body = closureBody("5", "user_finished", "epoch-1", "1", "1");
        String path = "/api/v1/care-executions/" + executionId + "/closure-confirmations";

        MvcResult[] results = concurrent(
                () -> CareAdmissionTestSupport.postJson(mockMvc, ctx.login().accessToken(), path,
                        "cc-a", body),
                () -> CareAdmissionTestSupport.postJson(mockMvc, ctx.login().accessToken(), path,
                        "cc-b", body));
        long successes = java.util.Arrays.stream(results)
                .filter(r -> r.getResponse().getStatus() == 200).count();
        long conflicts = java.util.Arrays.stream(results)
                .filter(r -> r.getResponse().getStatus() == 409).count();
        assertEquals(1, successes);
        assertEquals(1, conflicts);
        MvcResult conflict = results[0].getResponse().getStatus() == 409 ? results[0] : results[1];
        JsonNode error = JSON.readTree(conflict.getResponse().getContentAsString()).path("error");
        assertEquals("EXECUTION_NOT_RESUMABLE", error.path("code").asText());
        assertEquals("already_closed", error.path("details").path("reason").asText());
        assertEquals("closed", jdbc.queryForObject(
                "SELECT status FROM care_executions WHERE id = ?", String.class, executionId));
    }
}

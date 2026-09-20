package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.care.CareFaceVerifier.Outcome;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static cn.yuanxin.mvp.web.care.CareAdmissionTestSupport.PNG;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Part 1 人脸核验目标成员绑定与 fail-closed 证据（A03/A04 + 纯单元 + 上下文注入）。
 */
class CareFaceBindingIT extends AbstractCareIT {

    private static final String CAPABILITIES = CareTestFixtures.DEFAULT_CAPABILITIES;
    private static final String LATEST_OBS = "{\"schema_version\":1,\"epoch\":\"epoch-1\","
            + "\"seq\":\"2\",\"state\":\"paused\",\"occurred_at\":\"2026-09-10T04:00:00Z\","
            + "\"verification_revision\":\"1\",\"continuity_valid\":false,"
            + "\"continuity_invalidated\":true}";
    private static final String SNAPSHOT = "{\"schema_version\":1,"
            + "\"plan_id\":\"00000000-0000-0000-0000-000000000001\",\"target_count\":\"5\","
            + "\"summary\":null,\"execution_params\":{\"steps\":[{\"region\":\"face\"}]},"
            + "\"verification\":{\"purpose\":\"admission\"}}";

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    CareFaceVerifier injectedFaceVerifier;

    @Autowired
    ApplicationContext applicationContext;

    private CareTestFixtures fx;

    @org.junit.jupiter.api.BeforeEach
    void setUp() {
        fx = new CareTestFixtures(jdbc);
    }

    private record Ctx(LoginResult login, UUID memberId, UUID planId, UUID micro) {
    }

    private Ctx newCtx(String inst) throws Exception {
        LoginResult login = loginAppWithInstallation(newPhone(), inst);
        UUID memberId = fx.seedMember();
        fx.seedGrant(UUID.fromString(login.accountId()), memberId, "active");
        UUID gimbalId = fx.seedGimbal("face-g-" + UUID.randomUUID(), 1);
        UUID planId = fx.seedReadyPlan(fx.seedAssessment(gimbalId, memberId), memberId, 5, 0, 0, null);
        UUID micro = fx.seedMicrocrystal(CAPABILITIES);
        return new Ctx(login, memberId, planId, micro);
    }

    private String appMetadata(Ctx ctx) {
        return CareAdmissionTestSupport.admissionMetadata(ctx.micro(), "p", ctx.planId(), null, null,
                CareAdmissionTestSupport.capture("cap", "2026-09-10T04:00:00Z", "cc", "admission"),
                "consent");
    }

    private static JsonNode error(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString()).path("error");
    }

    private String t13Status(String key) {
        return jdbc.queryForObject("SELECT status FROM idempotency_requests WHERE idempotency_key = ?",
                String.class, key);
    }

    private UUID t13Id(String key) {
        return jdbc.queryForObject("SELECT id FROM idempotency_requests WHERE idempotency_key = ?",
                UUID.class, key);
    }

    @Test
    @DisplayName("(a) 绑定成员 X≠方案成员 Y → 403 FACE_NOT_VERIFIED：无 T07、T13 rejected、media 未挂 execution")
    void mismatchedMemberRejected() throws Exception {
        Ctx ctx = newCtx("face-mismatch");
        bindFaceMember(UUID.randomUUID()); // 异成员
        String key = CareAdmissionTestSupport.newKey();
        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, ctx.login().accessToken(), key,
                appMetadata(ctx), PNG);
        assertEquals(403, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("FACE_NOT_VERIFIED", error(r).path("code").asText());
        assertEquals("rejected", t13Status(key));
        assertEquals(0, jdbc.queryForObject(
                "SELECT count(*) FROM care_executions WHERE microcrystal_id = ?", Integer.class,
                ctx.micro()));
        // 目标成员确实传入 1:1 端口（绑定证据）
        assertEquals(ctx.memberId(), faceDouble.lastRequestedMemberId());
        // media 行存在（人脸已受理）但未挂执行
        var media = jdbc.queryForMap("SELECT state, execution_id FROM media_objects"
                + " WHERE purpose = 'execution_face' AND request_id = ?", t13Id(key));
        assertEquals("available", media.get("state"));
        assertNull(media.get("execution_id"));
    }

    @Test
    @DisplayName("(b) 未绑定成员 → 503 CAPABILITY_UNAVAILABLE fail-closed，T13 仍 processing")
    void unboundFailClosed() throws Exception {
        Ctx ctx = newCtx("face-unbound");
        faceDouble.reset();
        String key = CareAdmissionTestSupport.newKey();
        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, ctx.login().accessToken(), key,
                appMetadata(ctx), PNG);
        assertEquals(503, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("DEPENDENCY_UNAVAILABLE", error(r).path("code").asText());
        assertEquals("processing", t13Status(key));
        assertEquals(0, jdbc.queryForObject(
                "SELECT count(*) FROM care_executions WHERE microcrystal_id = ?", Integer.class,
                ctx.micro()));
    }

    @Test
    @DisplayName("(c) forceOutcome：UNCERTAIN→403、QUALITY_REJECTED→422、DEPENDENCY_FAILED→503")
    void forcedOutcomes() throws Exception {
        Ctx ctx = newCtx("face-forced");
        faceDouble.forceOutcome(Outcome.UNCERTAIN);
        MvcResult uncertain = CareAdmissionTestSupport.admit(mockMvc, ctx.login().accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(ctx), PNG);
        assertEquals(403, uncertain.getResponse().getStatus());
        assertEquals("FACE_NOT_VERIFIED", error(uncertain).path("code").asText());

        faceDouble.forceOutcome(Outcome.QUALITY_REJECTED);
        MvcResult quality = CareAdmissionTestSupport.admit(mockMvc, ctx.login().accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(ctx), PNG);
        assertEquals(422, quality.getResponse().getStatus());
        assertEquals("FACE_QUALITY_REJECTED", error(quality).path("code").asText());

        String key = CareAdmissionTestSupport.newKey();
        faceDouble.forceOutcome(Outcome.DEPENDENCY_FAILED);
        MvcResult dependency = CareAdmissionTestSupport.admit(mockMvc, ctx.login().accessToken(), key,
                appMetadata(ctx), PNG);
        assertEquals(503, dependency.getResponse().getStatus());
        assertEquals("DEPENDENCY_UNAVAILABLE", error(dependency).path("code").asText());
        assertEquals("processing", t13Status(key));
    }

    @Test
    @DisplayName("(d) 绑定方案成员 → 201 且返回 executionId")
    void boundMemberAdmitted() throws Exception {
        Ctx ctx = newCtx("face-bound");
        bindFaceMember(ctx.memberId());
        MvcResult r = CareAdmissionTestSupport.admit(mockMvc, ctx.login().accessToken(),
                CareAdmissionTestSupport.newKey(), appMetadata(ctx), PNG);
        assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode data = JSON.readTree(r.getResponse().getContentAsString()).path("data");
        assertNotNull(data.path("executionId").asText(null));
        assertEquals(ctx.memberId(), faceDouble.lastRequestedMemberId());
    }

    @Test
    @DisplayName("(e) A04 异成员 → 403 FACE_NOT_VERIFIED，revision 不变")
    void revalidationMismatchedMember() throws Exception {
        Ctx ctx = newCtx("face-a04-mismatch");
        UUID assessment = fx.seedAssessment(fx.seedGimbal("face-a04-g-" + UUID.randomUUID(), 1),
                ctx.memberId());
        UUID executionId = fx.execution(ctx.planId(), ctx.memberId(), ctx.micro(), assessment)
                .controllerApp(UUID.fromString(ctx.login().accountId()), "face-a04-mismatch")
                .status("paused").verificationRevision(1)
                .observation("epoch-1", 2, LATEST_OBS).planSnapshot(SNAPSHOT).insert();
        bindFaceMember(UUID.randomUUID()); // 异成员
        String request = CareAdmissionTestSupport.revalidationMetadata("1",
                CareAdmissionTestSupport.capture("cap", "2026-09-10T04:00:00Z", "cc", "revalidation"),
                "consent", null);
        MvcResult r = CareAdmissionTestSupport.revalidate(mockMvc, ctx.login().accessToken(),
                executionId, CareAdmissionTestSupport.newKey(), request, PNG);
        assertEquals(403, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("FACE_NOT_VERIFIED", error(r).path("code").asText());
        assertEquals(1L, ((Number) jdbc.queryForObject(
                "SELECT verification_revision FROM care_executions WHERE id = ?", Long.class,
                executionId)).longValue());
    }

    @Test
    @DisplayName("(f) 纯单元：FailClosedCareFaceVerifier 恒 CAPABILITY_UNAVAILABLE")
    void failClosedUnit() {
        assertEquals(Outcome.CAPABILITY_UNAVAILABLE,
                new FailClosedCareFaceVerifier().verifyOneToOne("admission", UUID.randomUUID(),
                        new byte[]{1, 2, 3}));
    }

    @Test
    @DisplayName("(g) 上下文注入：主 CareFaceVerifier 为替身且容器含 FailClosed bean")
    void beanWiring() {
        assertInstanceOf(MemberBindingFaceDouble.class, injectedFaceVerifier);
        assertNotNull(applicationContext.getBean(FailClosedCareFaceVerifier.class));
        assertTrue(applicationContext.getBean(CareFaceVerifier.class)
                instanceof MemberBindingFaceDouble);
    }
}

package cn.yuanxin.mvp.web.devices;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * 测试组 13：M2-A04 微晶观察登记（证明/归属/顺序/不越界）与 M2-A05 能力读取。
 */
class MicrocrystalObservationIT extends AbstractDeviceIT {

    private MvcResult observe(String token, String serial, String proof, String epoch, String seq,
                              String revision) throws Exception {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("microcrystalSerial", serial);
        body.put("connectionProof", proof);
        body.put("capabilities", Map.of("schemaVersion", 1, "revision", revision));
        body.put("observationEpoch", epoch);
        body.put("observationSeq", seq);
        body.put("observedAt", Instant.now().toString());
        body.put("state", Map.of("mode", "idle"));
        return mockMvc.perform(post("/api/v1/microcrystal-observations")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", "obs-" + UUID.randomUUID())
                        .contentType("application/json")
                        .content(writeJson(body)))
                .andReturn();
    }

    private MvcResult capabilities(String token, UUID microcrystalId, String proof) throws Exception {
        var request = get("/api/v1/microcrystals/" + microcrystalId + "/capabilities")
                .header("Authorization", "Bearer " + token);
        if (proof != null) {
            request = request.header("X-Connection-Proof", proof);
        }
        return mockMvc.perform(request).andReturn();
    }

    private Map<String, Object> microcrystalRow(UUID microcrystalId) {
        return jdbc.queryForMap("SELECT observer_type, observer_ref, observation_epoch,"
                + " observation_seq, capabilities::text AS capabilities,"
                + " latest_observation::text AS observation, received_at"
                + " FROM microcrystals WHERE id = ?", microcrystalId);
    }

    @Test
    @DisplayName("有效 connectionProof 登记；capabilities.schema_version 为 JSON 整数；observer 来自认证上下文")
    void validObservationRegistersCapabilities() throws Exception {
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-mc-valid");
        UUID account = UUID.fromString(app.accountId());
        String serial = "mc-" + UUID.randomUUID();
        long jobsBefore = count("async_jobs", "1 = 1");
        long executionsBefore = count("care_executions", "1 = 1");

        MvcResult result = observe(app.accessToken(), serial,
                DevProofFixture.connectionApp(account, "inst-mc-valid", serial), "e1", "1", "7");
        assertEquals(200, result.getResponse().getStatus(), result.getResponse().getContentAsString());
        assertTrue(dataOf(result).path("accepted").asBoolean());
        assertEquals("7", dataOf(result).path("capabilityRevision").asText());
        UUID microcrystalId = UUID.fromString(dataOf(result).path("microcrystalId").asText());

        Map<String, Object> row = microcrystalRow(microcrystalId);
        assertEquals("app_account", row.get("observer_type"));
        assertEquals(account + ":inst-mc-valid", row.get("observer_ref"));

        String schemaType = jdbc.queryForObject(
                "SELECT jsonb_typeof(capabilities -> 'schema_version') FROM microcrystals"
                        + " WHERE id = ?", String.class, microcrystalId);
        assertEquals("number", schemaType);
        assertEquals("1", jdbc.queryForObject(
                "SELECT capabilities ->> 'schema_version' FROM microcrystals WHERE id = ?",
                String.class, microcrystalId));
        assertEquals("7", jdbc.queryForObject(
                "SELECT capabilities ->> 'revision' FROM microcrystals WHERE id = ?",
                String.class, microcrystalId));

        // 不产生护理执行 / async_jobs
        assertEquals(jobsBefore, count("async_jobs", "1 = 1"));
        assertEquals(executionsBefore, count("care_executions", "1 = 1"));
        assertEquals(0, count("care_executions", "microcrystal_id = ?", microcrystalId));
    }

    @Test
    @DisplayName("证明缺失/结构非法/仅序列号 → 400；绑定别控制端 → 403；版本不支持 → 422；均不登记")
    void invalidProofsRejectedWithoutRegistration() throws Exception {
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-mc-bad");
        UUID account = UUID.fromString(app.accountId());

        String blankSerial = "mc-blank-" + UUID.randomUUID();
        assertEquals(400, observe(app.accessToken(), blankSerial, "", "e", "1", "1")
                .getResponse().getStatus());
        assertEquals(0, count("microcrystals", "serial_no = ?", blankSerial));

        String malformedSerial = "mc-malformed-" + UUID.randomUUID();
        assertEquals(400, observe(app.accessToken(), malformedSerial,
                DevProofFixture.malformedProof(), "e", "1", "1").getResponse().getStatus());
        assertEquals(0, count("microcrystals", "serial_no = ?", malformedSerial));

        // "仅提交序列号"：证明字段只放序列号 → 非证明结构 → 400（结构非法）
        String serialOnlySerial = "mc-serialonly-" + UUID.randomUUID();
        assertEquals(400, observe(app.accessToken(), serialOnlySerial, serialOnlySerial, "e", "1", "1")
                .getResponse().getStatus());
        assertEquals(0, count("microcrystals", "serial_no = ?", serialOnlySerial));

        String wrongObserverSerial = "mc-wrongobs-" + UUID.randomUUID();
        MvcResult wrongObserver = observe(app.accessToken(), wrongObserverSerial,
                DevProofFixture.connectionWrongObserver(wrongObserverSerial), "e", "1", "1");
        assertEquals(403, wrongObserver.getResponse().getStatus(),
                wrongObserver.getResponse().getContentAsString());
        assertEquals(0, count("microcrystals", "serial_no = ?", wrongObserverSerial));

        String unsupportedSerial = "mc-unsupported-" + UUID.randomUUID();
        assertEquals(422, observe(app.accessToken(), unsupportedSerial,
                DevProofFixture.connectionUnsupportedVersion(account, "inst-mc-bad", unsupportedSerial),
                "e", "1", "1").getResponse().getStatus());
        assertEquals(0, count("microcrystals", "serial_no = ?", unsupportedSerial));
    }

    @Test
    @DisplayName("observer 来自认证上下文：APP 后云台切换重置基准；未知顶层字段 400")
    void observerComesFromAuthNotBody() throws Exception {
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-mc-owner");
        UUID account = UUID.fromString(app.accountId());
        GimbalSession gimbal = gimbalSession();
        String serial = "mc-" + UUID.randomUUID();

        MvcResult appObs = observe(app.accessToken(), serial,
                DevProofFixture.connectionApp(account, "inst-mc-owner", serial), "e1", "5", "5");
        assertEquals(200, appObs.getResponse().getStatus(), appObs.getResponse().getContentAsString());
        UUID id = UUID.fromString(dataOf(appObs).path("microcrystalId").asText());
        assertEquals(account + ":inst-mc-owner", microcrystalRow(id).get("observer_ref"));

        // 不同来源（云台）+ 更小 seq → 接受并重置基准
        MvcResult gimbalObs = observe(gimbal.accessToken(), serial,
                DevProofFixture.connectionGimbal(gimbal.gimbalId(), serial), "e1", "1", "1");
        assertEquals(200, gimbalObs.getResponse().getStatus(),
                gimbalObs.getResponse().getContentAsString());
        assertTrue(dataOf(gimbalObs).path("accepted").asBoolean());
        assertEquals("gimbal", microcrystalRow(id).get("observer_type"));
        assertEquals(gimbal.gimbalId().toString(), microcrystalRow(id).get("observer_ref"));

        // 请求体伪造 observerRef（未知顶层字段）→ 400
        String forged = writeJson(Map.of(
                "microcrystalSerial", serial,
                "connectionProof", DevProofFixture.connectionGimbal(gimbal.gimbalId(), serial),
                "capabilities", Map.of("schemaVersion", 1, "revision", "9"),
                "observationEpoch", "e1",
                "observationSeq", "9",
                "observedAt", Instant.now().toString(),
                "state", Map.of("mode", "idle"),
                "observerRef", "forged-ref"));
        MvcResult rejected = mockMvc.perform(post("/api/v1/microcrystal-observations")
                        .header("Authorization", "Bearer " + gimbal.accessToken())
                        .header("Idempotency-Key", "obs-forge-" + UUID.randomUUID())
                        .contentType("application/json").content(forged))
                .andReturn();
        assertEquals(400, rejected.getResponse().getStatus());
        assertEquals(gimbal.gimbalId().toString(), microcrystalRow(id).get("observer_ref"));
    }

    @Test
    @DisplayName("旧 observation_seq → accepted=false 且不覆盖能力")
    void staleObservationDoesNotOverwriteCapabilities() throws Exception {
        LoginResult app = loginAppWithInstallation(newPhone(), "inst-mc-stale");
        UUID account = UUID.fromString(app.accountId());
        String serial = "mc-" + UUID.randomUUID();

        MvcResult fresh = observe(app.accessToken(), serial,
                DevProofFixture.connectionApp(account, "inst-mc-stale", serial), "e1", "5", "5");
        UUID id = UUID.fromString(dataOf(fresh).path("microcrystalId").asText());
        String before = (String) microcrystalRow(id).get("capabilities");

        MvcResult stale = observe(app.accessToken(), serial,
                DevProofFixture.connectionApp(account, "inst-mc-stale", serial), "e1", "3", "9");
        assertEquals(200, stale.getResponse().getStatus());
        assertFalse(dataOf(stale).path("accepted").asBoolean());
        assertEquals("5", dataOf(stale).path("capabilityRevision").asText());
        assertEquals(before, microcrystalRow(id).get("capabilities"));
    }

    @Test
    @DisplayName("APP 同 family 翻转 epoch/降 seq → 拒绝且 capabilities 未变；换安装实例（新 family）→ 接受并重置")
    void clientEpochIsNotAuthoritativeWithinGeneration() throws Exception {
        String phone = newPhone();
        String installationId = "inst-mc-epoch";
        LoginResult app = loginAppWithInstallation(phone, installationId);
        UUID account = UUID.fromString(app.accountId());
        String serial = "mc-" + UUID.randomUUID();
        long jobs = count("async_jobs", "1 = 1");
        long executions = count("care_executions", "1 = 1");

        MvcResult first = observe(app.accessToken(), serial,
                DevProofFixture.connectionApp(account, installationId, serial), "e1", "10", "1");
        assertTrue(dataOf(first).path("accepted").asBoolean());
        UUID id = UUID.fromString(dataOf(first).path("microcrystalId").asText());
        Map<String, Object> rowBefore = microcrystalRow(id);
        // APP 用稳定 family 作代次键：一个 account:installation 只占一个表项、generation=1
        assertEquals(1, observerSessionCount(id));
        assertEquals(1, observerGeneration(id));

        // 同 family（refresh 得到的新 sessionId）翻转 epoch + 降 seq → 拒绝且逐列未变
        LoginResult refreshed = loginAppWithInstallation(phone, installationId);
        assertEquals(account, UUID.fromString(refreshed.accountId()));
        MvcResult flipped = observe(refreshed.accessToken(), serial,
                DevProofFixture.connectionApp(account, installationId, serial), "e2", "1", "2");
        assertEquals(200, flipped.getResponse().getStatus());
        assertFalse(dataOf(flipped).path("accepted").asBoolean());
        assertEquals(rowBefore, microcrystalRow(id));

        // 同 family、epoch 不变但 seq 回退 → 拒绝且逐列未变
        MvcResult rollback = observe(refreshed.accessToken(), serial,
                DevProofFixture.connectionApp(account, installationId, serial), "e1", "9", "3");
        assertFalse(dataOf(rollback).path("accepted").asBoolean());
        assertEquals(rowBefore, microcrystalRow(id));
        assertEquals(1, observerSessionCount(id));

        // 真实来源推进：换安装实例 = 新 family → 新表项、更高 generation、接受并重置基准
        String newInstallation = installationId + "-2";
        LoginResult newFamily = loginAppWithInstallation(phone, newInstallation);
        assertEquals(account, UUID.fromString(newFamily.accountId()));
        MvcResult advanced = observe(newFamily.accessToken(), serial,
                DevProofFixture.connectionApp(account, newInstallation, serial), "e2", "1", "4");
        assertTrue(dataOf(advanced).path("accepted").asBoolean());
        assertEquals("4", dataOf(advanced).path("capabilityRevision").asText());
        assertEquals(account + ":" + newInstallation, microcrystalRow(id).get("observer_ref"));
        assertEquals(2, observerSessionCount(id));
        assertEquals(2, observerGeneration(id));
        assertEquals("number", jdbc.queryForObject(
                "SELECT jsonb_typeof(latest_observation -> 'schema_version')"
                        + " FROM microcrystals WHERE id = ?", String.class, id));
        assertEquals(jobs, count("async_jobs", "1 = 1"));
        assertEquals(executions, count("care_executions", "1 = 1"));
    }

    @Test
    @DisplayName("Oracle#4 微晶 APP：同一 account+installation 的多次 refresh/login 全部接受，表项恒为 1、generation 恒为 1")
    void appRefreshSessionsNeverExhaustFamilyTable() throws Exception {
        int max = deviceProps.maxObservationSessionsOrDefault();
        int attempts = Math.max(9, max + 1); // 超过上限的 session 数（Oracle 第 9 个），证明正常生命周期不累积、不耗尽
        String phone = newPhone();
        String installation = "inst-mc-refresh";
        String serial = "mc-" + UUID.randomUUID();
        Set<String> sessionIds = new LinkedHashSet<>();
        UUID account = null;
        UUID id = null;
        for (int i = 1; i <= attempts; i++) {
            // 每次 login 都是新的随机 sessionId，但 family（account:installation）不变
            LoginResult session = loginAppWithInstallation(phone, installation);
            account = UUID.fromString(session.accountId());
            sessionIds.add(sessionIdOf(session.accessToken()));
            MvcResult r = observe(session.accessToken(), serial,
                    DevProofFixture.connectionApp(account, installation, serial),
                    "E", String.valueOf(i), String.valueOf(i));
            assertTrue(dataOf(r).path("accepted").asBoolean(),
                    "refresh session " + i + " must be accepted (family must never exhaust)");
            if (id == null) {
                id = UUID.fromString(dataOf(r).path("microcrystalId").asText());
            }
        }
        assertTrue(sessionIds.size() >= 9,
                "must exercise at least 9 distinct APP sessions, got " + sessionIds.size());
        assertEquals(attempts, sessionIds.size(),
                "each login/refresh must issue a distinct sessionId");
        assertEquals(1, observerSessionCount(id),
                "same account:installation must occupy exactly one table entry");
        assertEquals(1, observerGeneration(id));
        assertEquals(account + ":" + installation, microcrystalRow(id).get("observer_ref"));
        assertEquals(String.valueOf(attempts), jdbc.queryForObject(
                "SELECT observation_seq::text FROM microcrystals WHERE id = ?",
                String.class, id));
    }

    @Test
    @DisplayName("Oracle#4 微晶：不同 family 交替不得来回覆盖，旧 family 永不重获权威")
    void olderSessionNeverRegainsAuthority() throws Exception {
        String phone = newPhone();
        String inst1 = "inst-mc-fam-1";
        String inst2 = "inst-mc-fam-2";
        LoginResult f1 = loginAppWithInstallation(phone, inst1);
        UUID account = UUID.fromString(f1.accountId());
        String serial = "mc-" + UUID.randomUUID();

        // family 1 首次 → generation=1
        MvcResult first = observe(f1.accessToken(), serial,
                DevProofFixture.connectionApp(account, inst1, serial), "E", "100", "1");
        assertTrue(dataOf(first).path("accepted").asBoolean());
        UUID id = UUID.fromString(dataOf(first).path("microcrystalId").asText());
        String capsAfterFirst = (String) microcrystalRow(id).get("capabilities");

        // family 2（不同安装实例）→ 新表项 generation=2，接受并重置基准
        LoginResult f2 = loginAppWithInstallation(phone, inst2);
        assertEquals(account, UUID.fromString(f2.accountId()));
        MvcResult second = observe(f2.accessToken(), serial,
                DevProofFixture.connectionApp(account, inst2, serial), "E2", "1", "2");
        assertTrue(dataOf(second).path("accepted").asBoolean());
        String capsAfterSecond = (String) microcrystalRow(id).get("capabilities");
        assertFalse(capsAfterFirst.equals(capsAfterSecond));
        assertEquals(2, observerSessionCount(id));
        assertEquals(2, observerGeneration(id));
        Map<String, Object> rowAfterSecond = microcrystalRow(id);

        // 关键：旧 family 1 再报（epoch+seq 看似更"新"）不得重获权威 → 拒绝且逐列未变
        MvcResult stale = observe(f1.accessToken(), serial,
                DevProofFixture.connectionApp(account, inst1, serial), "E", "101", "3");
        assertEquals(200, stale.getResponse().getStatus());
        assertFalse(dataOf(stale).path("accepted").asBoolean());
        assertEquals(rowAfterSecond, microcrystalRow(id));

        // 当前 family 2 同 family 内继续推进
        MvcResult next = observe(f2.accessToken(), serial,
                DevProofFixture.connectionApp(account, inst2, serial), "E2", "2", "4");
        assertTrue(dataOf(next).path("accepted").asBoolean());
        assertEquals("4", dataOf(next).path("capabilityRevision").asText());
    }

    @Test
    @DisplayName("Oracle#4 微晶 APP：不同 family 表满后未见 family fail closed 且不写；在表 family 不受影响")
    void sessionTableFullFailClosed() throws Exception {
        int max = deviceProps.maxObservationSessionsOrDefault();
        String phone = newPhone();
        String serial = "mc-" + UUID.randomUUID();
        List<LoginResult> families = new ArrayList<>();
        List<String> installations = new ArrayList<>();
        UUID account = null;
        UUID id = null;
        for (int i = 0; i < max; i++) {
            String installation = "inst-mc-full-" + i;
            LoginResult family = loginAppWithInstallation(phone, installation);
            families.add(family);
            installations.add(installation);
            account = UUID.fromString(family.accountId());
            MvcResult r = observe(family.accessToken(), serial,
                    DevProofFixture.connectionApp(account, installation, serial),
                    "e" + i, "1", String.valueOf(i + 1));
            assertTrue(dataOf(r).path("accepted").asBoolean(), "family " + i + " must be accepted");
            if (id == null) {
                id = UUID.fromString(dataOf(r).path("microcrystalId").asText());
            }
        }
        String capsFilled = (String) microcrystalRow(id).get("capabilities");
        assertEquals(max, observerSessionCount(id));

        // 第 max+1 个未见 family → fail closed，不追加、capabilities 未变
        String overflowInstallation = "inst-mc-full-overflow";
        LoginResult overflow = loginAppWithInstallation(phone, overflowInstallation);
        MvcResult rejected = observe(overflow.accessToken(), serial,
                DevProofFixture.connectionApp(account, overflowInstallation, serial),
                "eNew", "1", "99");
        assertEquals(200, rejected.getResponse().getStatus());
        assertFalse(dataOf(rejected).path("accepted").asBoolean());
        assertEquals(capsFilled, microcrystalRow(id).get("capabilities"));
        assertEquals(max, observerSessionCount(id), "rejected unseen family must not be appended");

        // 在表中的 family（最后一个）不受影响：同 family、严格更大 seq → 接受
        MvcResult current = observe(families.get(max - 1).accessToken(), serial,
                DevProofFixture.connectionApp(account, installations.get(max - 1), serial),
                "e" + (max - 1), "2", "100");
        assertTrue(dataOf(current).path("accepted").asBoolean(),
                "table-full must not reject an already-tracked family");
    }

    private int observerSessionCount(UUID microcrystalId) {
        return jdbc.queryForObject(
                "SELECT jsonb_array_length(latest_observation -> 'observer_sessions')"
                        + " FROM microcrystals WHERE id = ?", Integer.class, microcrystalId);
    }

    private int observerGeneration(UUID microcrystalId) {
        return jdbc.queryForObject(
                "SELECT (latest_observation ->> 'observer_generation')::int"
                        + " FROM microcrystals WHERE id = ?", Integer.class, microcrystalId);
    }

    @Test
    @DisplayName("M2-A05：observer 可读、无证明无上下文 403、他人/不存在 404 不可区分、isStale 正确")
    void capabilitiesAccessControl() throws Exception {
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-mc-cap-owner");
        UUID ownerAccount = UUID.fromString(owner.accountId());
        String serial = "mc-" + UUID.randomUUID();
        MvcResult observed = observe(owner.accessToken(), serial,
                DevProofFixture.connectionApp(ownerAccount, "inst-mc-cap-owner", serial),
                "e1", "1", "3");
        UUID id = UUID.fromString(dataOf(observed).path("microcrystalId").asText());
        String before = (String) microcrystalRow(id).get("capabilities");

        // 同 observer 无证明（上下文推定）→ 200
        MvcResult implicit = capabilities(owner.accessToken(), id, null);
        assertEquals(200, implicit.getResponse().getStatus(), implicit.getResponse().getContentAsString());
        assertFalse(dataOf(implicit).path("capabilities").path("schema_version").isMissingNode());
        assertEquals("3", dataOf(implicit).path("capabilityRevision").asText());
        assertFalse(dataOf(implicit).path("isStale").asBoolean());

        // 同 observer 合法证明 → 200
        assertEquals(200, capabilities(owner.accessToken(), id,
                DevProofFixture.connectionApp(ownerAccount, "inst-mc-cap-owner", serial))
                .getResponse().getStatus());

        // 他人无证明 → 404；不存在 → 404，逐字一致
        LoginResult stranger = loginAppWithInstallation(newPhone(), "inst-mc-cap-stranger");
        MvcResult foreign = capabilities(stranger.accessToken(), id, null);
        MvcResult missing = capabilities(stranger.accessToken(), UUID.randomUUID(), null);
        assertEquals(404, foreign.getResponse().getStatus());
        assertIndistinguishableError(foreign, missing);

        // 从未被观察的微晶 + 无证明 → 403（无上下文可推定）
        UUID freshId = UUID.randomUUID();
        String freshSerial = "mc-never-" + freshId;
        jdbc.update("INSERT INTO microcrystals (id, serial_no) VALUES (?, ?)", freshId, freshSerial);
        assertEquals(403, capabilities(owner.accessToken(), freshId, null).getResponse().getStatus());

        // 非法证明 → 403；绑定别的微晶的证明 → 404
        assertEquals(403, capabilities(owner.accessToken(), id,
                DevProofFixture.malformedProof()).getResponse().getStatus());
        assertEquals(404, capabilities(owner.accessToken(), id,
                DevProofFixture.connectionWrongMicrocrystal(ownerAccount, "inst-mc-cap-owner", serial))
                .getResponse().getStatus());

        // GET 无副作用
        assertEquals(before, microcrystalRow(id).get("capabilities"));

        // isStale 超阈值
        jdbc.update("UPDATE microcrystals SET received_at = now() - interval '2 hours' WHERE id = ?", id);
        assertTrue(dataOf(capabilities(owner.accessToken(), id, null)).path("isStale").asBoolean());
    }
}

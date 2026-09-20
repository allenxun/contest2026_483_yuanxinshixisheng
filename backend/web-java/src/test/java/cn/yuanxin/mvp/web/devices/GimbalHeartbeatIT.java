package cn.yuanxin.mvp.web.devices;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * 测试组 2-6：M2-A02 心跳顺序、越权、不越界、episode 稳定性、状态变化代次。
 */
class GimbalHeartbeatIT extends AbstractDeviceIT {

    private MvcResult heartbeat(String token, UUID gimbalId, String epoch, String seq,
                                Object incidents) throws Exception {
        return mockMvc.perform(post("/api/v1/gimbals/" + gimbalId + "/heartbeats")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json")
                        .content(heartbeatJson(epoch, seq, "awake", null, null, incidents)))
                .andReturn();
    }

    private Map<String, Object> row(UUID gimbalId) {
        return jdbc.queryForMap("SELECT last_seen_at, status_revision, connection_status,"
                + " latest_observation::text AS obs, active_incidents::text AS incidents"
                + " FROM gimbals WHERE id = ?", gimbalId);
    }

    @Test
    @DisplayName("测试组 2：seq 推进；重放/迟到不推进；新 epoch 重置基准")
    void orderingRejectsStaleAndDuplicate() throws Exception {
        GimbalSession session = gimbalSession();
        UUID gimbalId = session.gimbalId();
        String token = session.accessToken();

        assertEquals(200, heartbeat(token, gimbalId, "epoch-1", "1", null)
                .getResponse().getStatus());
        assertTrue(dataOf(heartbeat(token, gimbalId, "epoch-1", "2", null))
                .path("accepted").asBoolean());
        assertTrue(dataOf(heartbeat(token, gimbalId, "epoch-1", "3", null))
                .path("accepted").asBoolean());

        Map<String, Object> before = row(gimbalId);
        MvcResult duplicate = heartbeat(token, gimbalId, "epoch-1", "2", null);
        assertEquals(200, duplicate.getResponse().getStatus());
        assertFalse(dataOf(duplicate).path("accepted").asBoolean());
        assertFalse(dataOf(duplicate).path("lastSeenAt").asText().isBlank());
        // 旧/重复心跳不推进：DB 逐列未变
        assertEquals(before, row(gimbalId));

        MvcResult late = heartbeat(token, gimbalId, "epoch-1", "1", null);
        assertFalse(dataOf(late).path("accepted").asBoolean());
        assertEquals(before, row(gimbalId));

        // 同一服务端会话代次内换 epoch → 不是新来源，拒绝且逐列未变
        MvcResult epochFlip = heartbeat(token, gimbalId, "epoch-2", "1", null);
        assertEquals(200, epochFlip.getResponse().getStatus());
        assertFalse(dataOf(epochFlip).path("accepted").asBoolean());
        assertEquals(before, row(gimbalId));
    }

    @Test
    @DisplayName("代次权威：同会话翻转 epoch/回退/重复 seq 拒绝且逐列未变；credential_version 推进后接受并重置")
    void clientEpochIsNotAuthoritativeWithinGeneration() throws Exception {
        GimbalSession session = gimbalSession();
        UUID gimbalId = session.gimbalId();
        String token = session.accessToken();

        // 先 epoch=E2, seq=100 接受
        assertTrue(dataOf(heartbeat(token, gimbalId, "E2", "100", null))
                .path("accepted").asBoolean());
        assertNotNull(jdbc.queryForObject(
                "SELECT latest_observation ->> 'observation_generation' FROM gimbals WHERE id = ?",
                String.class, gimbalId));
        assertEquals("number", jdbc.queryForObject(
                "SELECT jsonb_typeof(latest_observation -> 'schema_version') FROM gimbals WHERE id = ?",
                String.class, gimbalId));
        Map<String, Object> after100 = row(gimbalId);

        // 同会话换 epoch + 更小 seq（客户端自填 epoch 不是权威）→ 拒绝，逐列未变
        MvcResult epochFlip = heartbeat(token, gimbalId, "E1", "1", null);
        assertEquals(200, epochFlip.getResponse().getStatus());
        assertFalse(dataOf(epochFlip).path("accepted").asBoolean());
        assertEquals(after100, row(gimbalId));

        // 同 epoch、seq 回退 → 拒绝，逐列未变
        MvcResult rollback = heartbeat(token, gimbalId, "E2", "99", null);
        assertFalse(dataOf(rollback).path("accepted").asBoolean());
        assertEquals(after100, row(gimbalId));

        // 同 epoch、seq 重复 → 拒绝，逐列未变
        MvcResult duplicate = heartbeat(token, gimbalId, "E2", "100", null);
        assertFalse(dataOf(duplicate).path("accepted").asBoolean());
        assertEquals(after100, row(gimbalId));

        // 真实代次推进：DB 递增 credential_version 并重新认证取新 token → 接受并重置
        jdbc.update("UPDATE gimbals SET credential_version = credential_version + 1 WHERE id = ?",
                gimbalId);
        String newToken = gimbalToken(gimbalId, 2L);
        MvcResult advanced = heartbeat(newToken, gimbalId, "E3", "1", null);
        assertEquals(200, advanced.getResponse().getStatus(),
                advanced.getResponse().getContentAsString());
        assertTrue(dataOf(advanced).path("accepted").asBoolean());
        Map<String, Object> afterAdvance = row(gimbalId);
        assertFalse(after100.get("last_seen_at").equals(afterAdvance.get("last_seen_at")));
        assertNotNull(jdbc.queryForObject(
                "SELECT latest_observation ->> 'observation_generation' FROM gimbals WHERE id = ?",
                String.class, gimbalId));
    }

    @Test
    @DisplayName("Oracle#2：同 credential_version 下两会话交替不得来回覆盖，旧会话永不重获权威")
    void olderSessionNeverRegainsAuthority() throws Exception {
        UUID gimbalId = seedGimbal(1L);
        // 同一 credential_version 下两个均未被撤销的 session（签发新 session 不使旧 session 失效）
        String tokenA = gimbalToken(gimbalId, 1L);
        String tokenB = gimbalToken(gimbalId, 1L);

        // 会话 A 服务端首次见到 → generation=1
        assertTrue(dataOf(heartbeat(tokenA, gimbalId, "EA", "100", null))
                .path("accepted").asBoolean());
        Map<String, Object> afterA = row(gimbalId);

        // 会话 B 服务端首次见到 → generation=2（更高），接受并重置基准
        assertTrue(dataOf(heartbeat(tokenB, gimbalId, "EB", "1", null))
                .path("accepted").asBoolean());
        Map<String, Object> afterB = row(gimbalId);
        assertFalse(afterA.get("last_seen_at").equals(afterB.get("last_seen_at")));

        // 关键：A 再报（更高 seq、同 epoch）不得重获权威 → 拒绝且逐列未变
        MvcResult aAgain = heartbeat(tokenA, gimbalId, "EA", "101", null);
        assertEquals(200, aAgain.getResponse().getStatus());
        assertFalse(dataOf(aAgain).path("accepted").asBoolean());
        assertEquals(afterB, row(gimbalId));

        // B 同连接内继续推进（epoch 一致、seq 严格更大）
        assertTrue(dataOf(heartbeat(tokenB, gimbalId, "EB", "2", null))
                .path("accepted").asBoolean());

        // 会话表记录服务端实际见过的两个 session，当前 generation=2
        assertEquals(2, ((Number) jdbc.queryForObject(
                "SELECT jsonb_array_length(latest_observation -> 'observation_sessions')"
                        + " FROM gimbals WHERE id = ?", Integer.class, gimbalId)).intValue());
        assertEquals(2, ((Number) jdbc.queryForObject(
                "SELECT (latest_observation ->> 'observation_generation')::int"
                        + " FROM gimbals WHERE id = ?", Integer.class, gimbalId)).intValue());
    }

    @Test
    @DisplayName("Oracle#3 会话表有界：表长恰为上限，第 max+1..max+3 个未见 session 被拒且不入表")
    void sessionTableIsBounded() throws Exception {
        int max = deviceProps.maxObservationSessionsOrDefault();
        UUID gimbalId = seedGimbal(1L);
        List<String> tokens = new ArrayList<>();
        for (int i = 0; i < max + 3; i++) {
            String token = gimbalToken(gimbalId, 1L);
            tokens.add(token);
            boolean accepted = dataOf(heartbeat(token, gimbalId, "e" + i, "1", null))
                    .path("accepted").asBoolean();
            if (i < max) {
                assertTrue(accepted, "session " + i + " (in table) must be accepted");
            } else {
                assertFalse(accepted, "session " + i + " (table full, unseen) must be rejected");
                assertFalse(sessionPresent(sessionIdOf(token), gimbalId),
                        "rejected unseen session must NOT be appended");
            }
        }
        // 表长恰为上限（不淘汰、不追加），最高 generation 属于第 max 个 session
        assertEquals(max, jdbc.queryForObject(
                "SELECT jsonb_array_length(latest_observation -> 'observation_sessions')"
                        + " FROM gimbals WHERE id = ?", Integer.class, gimbalId));
        assertEquals(max, jdbc.queryForObject(
                "SELECT (latest_observation ->> 'observation_generation')::int"
                        + " FROM gimbals WHERE id = ?", Integer.class, gimbalId));
        assertTrue(sessionPresent(sessionIdOf(tokens.get(max - 1)), gimbalId),
                "highest-generation session must be retained");
        assertTrue(sessionPresent(sessionIdOf(tokens.get(0)), gimbalId),
                "oldest session must NOT be pruned (table only grows until credential advance)");
    }

    @Test
    @DisplayName("Oracle#3：表满后未见 session fail closed 且不淘汰旧 session；当前连接不受影响；仅凭据推进可恢复")
    void sessionTableFullFailClosedAndRecovery() throws Exception {
        int max = deviceProps.maxObservationSessionsOrDefault();
        UUID gimbalId = seedGimbal(1L);

        // 前 max 个 session 依次被服务端见到并入表（generation 1..max）
        List<String> tokens = new ArrayList<>();
        for (int i = 0; i < max; i++) {
            String token = gimbalToken(gimbalId, 1L);
            tokens.add(token);
            assertTrue(dataOf(heartbeat(token, gimbalId, "e" + i, "1", null))
                    .path("accepted").asBoolean(), "session " + i + " must be accepted");
        }
        Map<String, Object> afterFilled = row(gimbalId);
        assertEquals(max, sessionCount(gimbalId));

        // 第 max+1 个 = 未见 session → fail closed，不追加、不写任何列（Oracle 确切复现第 9 个）
        String overflowToken = gimbalToken(gimbalId, 1L);
        MvcResult overflow = heartbeat(overflowToken, gimbalId, "eNew", "1", null);
        assertEquals(200, overflow.getResponse().getStatus());
        assertFalse(dataOf(overflow).path("accepted").asBoolean());
        assertEquals(afterFilled, row(gimbalId), "rejected unseen session must not change any column");
        assertEquals(max, sessionCount(gimbalId), "rejected unseen session must not be appended");
        assertFalse(sessionPresent(sessionIdOf(overflowToken), gimbalId));

        // 表满不影响当前合法连接：最高 generation 的 session 同 epoch、严格更大 seq → 接受且推进
        Map<String, Object> beforeCurrent = row(gimbalId);
        MvcResult current = heartbeat(tokens.get(max - 1), gimbalId, "e" + (max - 1), "2", null);
        assertTrue(dataOf(current).path("accepted").asBoolean(),
                "table-full must not reject the current connection");
        assertFalse(beforeCurrent.get("last_seen_at").equals(row(gimbalId).get("last_seen_at")));

        // 再用第一个 token（仍在表中、generation=1 < 当前）→ 仍拒绝且逐列未变
        Map<String, Object> beforeFirstAgain = row(gimbalId);
        MvcResult firstAgain = heartbeat(tokens.get(0), gimbalId, "e0", "100", null);
        assertEquals(200, firstAgain.getResponse().getStatus());
        assertFalse(dataOf(firstAgain).path("accepted").asBoolean(),
                "evicted-then-stale first session must never regain authority");
        assertEquals(beforeFirstAgain, row(gimbalId));

        // 唯一恢复途径：credential_version 严格推进 → 清空会话表，新 session=gen1、接受并重置
        jdbc.update("UPDATE gimbals SET credential_version = credential_version + 1 WHERE id = ?",
                gimbalId);
        String recoveryToken = gimbalToken(gimbalId, 2L);
        MvcResult recovered = heartbeat(recoveryToken, gimbalId, "r", "1", null);
        assertEquals(200, recovered.getResponse().getStatus(),
                recovered.getResponse().getContentAsString());
        assertTrue(dataOf(recovered).path("accepted").asBoolean());
        assertEquals(1, sessionCount(gimbalId), "credential advance must clear the session table");
        assertEquals(1, jdbc.queryForObject(
                "SELECT (latest_observation ->> 'observation_generation')::int"
                        + " FROM gimbals WHERE id = ?", Integer.class, gimbalId));
    }

    private int sessionCount(UUID gimbalId) {
        return jdbc.queryForObject(
                "SELECT jsonb_array_length(latest_observation -> 'observation_sessions')"
                        + " FROM gimbals WHERE id = ?", Integer.class, gimbalId);
    }

    private boolean sessionPresent(String sessionId, UUID gimbalId) {
        Boolean present = jdbc.queryForObject(
                "SELECT EXISTS (SELECT 1 FROM jsonb_array_elements("
                        + "latest_observation -> 'observation_sessions') e"
                        + " WHERE e ->> 'session_id' = ?) FROM gimbals WHERE id = ?",
                Boolean.class, sessionId, gimbalId);
        return Boolean.TRUE.equals(present);
    }

    @Test
    @DisplayName("测试组 3：APP → 403；他人云台/不存在 → 不可区分 404；无 token → 401")
    void authorization() throws Exception {
        GimbalSession a = gimbalSession();
        GimbalSession b = gimbalSession();
        String appToken = loginApp(newPhone());

        MvcResult app = heartbeat(appToken, a.gimbalId(), "e", "1", null);
        assertEquals(403, app.getResponse().getStatus());
        assertEquals("CALLER_NOT_ALLOWED", errorOf(app).path("code").asText());

        MvcResult foreign = heartbeat(b.accessToken(), a.gimbalId(), "e", "1", null);
        MvcResult missing = heartbeat(b.accessToken(), UUID.randomUUID(), "e", "1", null);
        assertIndistinguishableError(foreign, missing);
        assertEquals(404, foreign.getResponse().getStatus());
        assertEquals("RESOURCE_NOT_VISIBLE", errorOf(foreign).path("code").asText());

        MvcResult anonymous = mockMvc.perform(post("/api/v1/gimbals/" + a.gimbalId() + "/heartbeats")
                        .contentType("application/json")
                        .content(heartbeatJson("e", "1", "awake", null, null, null)))
                .andReturn();
        assertEquals(401, anonymous.getResponse().getStatus());
    }

    @Test
    @DisplayName("测试组 4：taskId/executionId 只作观察，不移动指针/不建执行/不建 job/不建通知")
    void heartbeatDoesNotCrossIntoTaskState() throws Exception {
        GimbalSession session = gimbalSession();
        UUID gimbalId = session.gimbalId();
        long executions = count("care_executions", "controller_gimbal_id = ?", gimbalId);
        long jobs = count("async_jobs", "owner_id = ?", gimbalId);
        long notifications = count("notifications", "gimbal_id = ?", gimbalId);

        MvcResult result = mockMvc.perform(post("/api/v1/gimbals/" + gimbalId + "/heartbeats")
                        .header("Authorization", "Bearer " + session.accessToken())
                        .contentType("application/json")
                        .content(heartbeatJson("e", "1", "awake", UUID.randomUUID(),
                                UUID.randomUUID(), null)))
                .andReturn();
        assertEquals(200, result.getResponse().getStatus());
        assertTrue(dataOf(result).path("accepted").asBoolean());

        Map<String, Object> row = jdbc.queryForMap("SELECT current_assessment_id,"
                + " current_assessment_revision, latest_observation::text AS obs"
                + " FROM gimbals WHERE id = ?", gimbalId);
        assertNull(row.get("current_assessment_id"));
        assertEquals(0L, ((Number) row.get("current_assessment_revision")).longValue());
        JsonNode observed = JSON.readTree((String) row.get("obs"));
        assertNotNull(observed.path("task_ref").asText(null));
        assertEquals(executions, count("care_executions", "controller_gimbal_id = ?", gimbalId));
        assertEquals(jobs, count("async_jobs", "owner_id = ?", gimbalId));
        assertEquals(notifications, count("notifications", "gimbal_id = ?", gimbalId));
    }

    @Test
    @DisplayName("测试组 5：同 code 一个 episode、同一 incidentId；清除 resolved；再现新 ID")
    void episodesAreStable() throws Exception {
        GimbalSession session = gimbalSession();
        UUID gimbalId = session.gimbalId();
        String token = session.accessToken();
        List<Map<String, Object>> incident = List.of(Map.of("code", "OVERHEAT", "severity", "high"));

        for (int seq = 1; seq <= 3; seq++) {
            assertTrue(dataOf(heartbeat(token, gimbalId, "e", String.valueOf(seq), incident))
                    .path("accepted").asBoolean());
        }
        JsonNode active = JSON.readTree((String) row(gimbalId).get("incidents")).path("episodes");
        assertEquals(1, active.size());
        String firstId = active.fieldNames().next();
        assertEquals("active", active.path(firstId).path("state").asText());

        // 报清除
        MvcResult cleared = heartbeat(token, gimbalId, "e", "4",
                List.of(Map.of("code", "OVERHEAT", "state", "cleared")));
        assertEquals(200, cleared.getResponse().getStatus());
        JsonNode afterClear = JSON.readTree((String) row(gimbalId).get("incidents")).path("episodes");
        assertEquals(1, afterClear.size());
        assertEquals("resolved", afterClear.path(firstId).path("state").asText());
        assertFalse(afterClear.path(firstId).path("resolved_at").isNull());

        // 再现同 code → 新 incidentId
        heartbeat(token, gimbalId, "e", "5", List.of(Map.of("code", "OVERHEAT")));
        JsonNode afterReoccur = JSON.readTree((String) row(gimbalId).get("incidents")).path("episodes");
        assertEquals(2, afterReoccur.size());
        String secondId = null;
        for (var it = afterReoccur.fieldNames(); it.hasNext(); ) {
            String id = it.next();
            if (!id.equals(firstId)) {
                secondId = id;
            }
        }
        assertNotNull(secondId);
        assertEquals("active", afterReoccur.path(secondId).path("state").asText());
    }

    @Test
    @DisplayName("测试组 6：unknown→online 时 status_revision +1；同状态不递增")
    void statusRevisionOnlyOnConnectionChange() throws Exception {
        GimbalSession session = gimbalSession();
        UUID gimbalId = session.gimbalId();
        String token = session.accessToken();

        heartbeat(token, gimbalId, "e", "1", null);
        Map<String, Object> afterFirst = row(gimbalId);
        assertEquals("online", afterFirst.get("connection_status"));
        assertEquals(1L, ((Number) afterFirst.get("status_revision")).longValue());

        heartbeat(token, gimbalId, "e", "2", null);
        assertEquals(1L, ((Number) row(gimbalId).get("status_revision")).longValue());
    }
}

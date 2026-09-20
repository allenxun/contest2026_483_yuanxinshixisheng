package cn.yuanxin.mvp.web.devices;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

/**
 * 测试组 8-12、14：M2-A06 绑定（并发/幂等/代次/证明）、M2-A07 绑定状态、
 * M2-A08 解绑语义、绑定不等于成员授权。
 */
class GimbalBindingIT extends AbstractDeviceIT {

    private MvcResult putBind(String token, UUID gimbalId, String key, String expectedRevision,
                              String proof) throws Exception {
        String body = proof == null
                ? "{\"expectedBindingRevision\":\"" + expectedRevision + "\"}"
                : writeJson(Map.of("expectedBindingRevision", expectedRevision,
                        "pairingProof", proof));
        return mockMvc.perform(put("/api/v1/me/gimbal-bindings/" + gimbalId)
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key)
                        .contentType("application/json")
                        .content(body))
                .andReturn();
    }

    private MvcResult getBindingStatus(String token, UUID gimbalId, String proof) throws Exception {
        var request = get("/api/v1/gimbals/" + gimbalId + "/binding-status")
                .header("Authorization", "Bearer " + token);
        if (proof != null) {
            request = request.header("X-Pairing-Proof", proof);
        }
        return mockMvc.perform(request).andReturn();
    }

    private MvcResult deleteUnbind(String token, UUID gimbalId, String key, String ifMatch)
            throws Exception {
        var request = delete("/api/v1/me/gimbal-bindings/" + gimbalId)
                .header("Authorization", "Bearer " + token)
                .header("Idempotency-Key", key);
        if (ifMatch != null) {
            request = request.header("If-Match", ifMatch);
        }
        return mockMvc.perform(request).andReturn();
    }

    private Map<String, Object> bindingRow(UUID gimbalId) {
        return jdbc.queryForMap("SELECT bound_account_id, binding_revision, bound_at,"
                + " current_assessment_id, current_assessment_revision FROM gimbals WHERE id = ?",
                gimbalId);
    }

    private void assertUnboundAndUnchanged(UUID gimbalId) {
        Map<String, Object> row = bindingRow(gimbalId);
        assertNull(row.get("bound_account_id"));
        assertEquals(0L, ((Number) row.get("binding_revision")).longValue());
        assertNull(row.get("bound_at"));
    }

    @Test
    @DisplayName("测试组 8：两账号真实并发绑定，恰好一个成功且 binding_revision 只 +1")
    void concurrentBindExactlyOneWins() throws Exception {
        UUID gimbalId = seedGimbal();
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-race-a");
        LoginResult b = loginAppWithInstallation(newPhone(), "inst-race-b");
        UUID accountA = UUID.fromString(a.accountId());
        UUID accountB = UUID.fromString(b.accountId());
        String proofA = DevProofFixture.pairingValid(gimbalId, accountA, "inst-race-a");
        String proofB = DevProofFixture.pairingValid(gimbalId, accountB, "inst-race-b");

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<MvcResult> callA = () -> {
                ready.countDown();
                go.await();
                return putBind(a.accessToken(), gimbalId, "race-a-" + gimbalId, "0", proofA);
            };
            Callable<MvcResult> callB = () -> {
                ready.countDown();
                go.await();
                return putBind(b.accessToken(), gimbalId, "race-b-" + gimbalId, "0", proofB);
            };
            Future<MvcResult> futureA = pool.submit(callA);
            Future<MvcResult> futureB = pool.submit(callB);
            assertTrue(ready.await(30, TimeUnit.SECONDS));
            go.countDown();
            MvcResult resultA = futureA.get(60, TimeUnit.SECONDS);
            MvcResult resultB = futureB.get(60, TimeUnit.SECONDS);

            List<Integer> statuses = new ArrayList<>(List.of(
                    resultA.getResponse().getStatus(), resultB.getResponse().getStatus()));
            statuses.sort(Integer::compareTo);
            assertEquals(List.of(200, 409), statuses);
            MvcResult loser = resultA.getResponse().getStatus() == 409 ? resultA : resultB;
            assertTrue(Set.of("BOUND_TO_OTHER", "BINDING_CHANGED")
                    .contains(errorOf(loser).path("code").asText()));
        } finally {
            pool.shutdownNow();
        }

        Map<String, Object> row = bindingRow(gimbalId);
        UUID bound = (UUID) row.get("bound_account_id");
        assertNotNull(bound);
        assertTrue(bound.equals(accountA) || bound.equals(accountB));
        assertEquals(1L, ((Number) row.get("binding_revision")).longValue());
    }

    @Test
    @DisplayName("测试组 9：重复绑定幂等不递增；过期代次 BINDING_CHANGED；他人 BOUND_TO_OTHER；T13 冲突")
    void bindIdempotencyAndRevisionGuards() throws Exception {
        UUID gimbalId = seedGimbal();
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-idem-a");
        LoginResult b = loginAppWithInstallation(newPhone(), "inst-idem-b");
        UUID accountA = UUID.fromString(a.accountId());
        UUID accountB = UUID.fromString(b.accountId());
        String instA = "inst-idem-a";

        MvcResult first = putBind(a.accessToken(), gimbalId, "idem-first-" + gimbalId, "0",
                DevProofFixture.pairingValid(gimbalId, accountA, instA));
        assertEquals(200, first.getResponse().getStatus(), first.getResponse().getContentAsString());
        assertEquals("1", dataOf(first).path("bindingRevision").asText());
        assertEquals("self", dataOf(first).path("bindingStatus").asText());
        assertFalse(dataOf(first).path("boundAt").isNull());

        // 同账号同代次重复绑定 → 200 同 revision，DB 未递增
        MvcResult repeat = putBind(a.accessToken(), gimbalId, "idem-repeat-" + gimbalId, "1",
                DevProofFixture.pairingValid(gimbalId, accountA, instA));
        assertEquals(200, repeat.getResponse().getStatus());
        assertEquals("1", dataOf(repeat).path("bindingRevision").asText());
        assertEquals(1L, ((Number) bindingRow(gimbalId).get("binding_revision")).longValue());

        // 过期预期代次 → 409 BINDING_CHANGED，含 currentBindingRevision，不含他人账号
        MvcResult stale = putBind(a.accessToken(), gimbalId, "idem-stale-" + gimbalId, "0",
                DevProofFixture.pairingValid(gimbalId, accountA, instA));
        assertEquals(409, stale.getResponse().getStatus());
        assertEquals("BINDING_CHANGED", errorOf(stale).path("code").asText());
        assertEquals("1", errorOf(stale).path("details").path("currentBindingRevision").asText());
        assertFalse(stale.getResponse().getContentAsString().contains(accountB.toString()));

        // 他人已绑定 → 409 BOUND_TO_OTHER，原绑定保持
        MvcResult other = putBind(b.accessToken(), gimbalId, "idem-other-" + gimbalId, "1",
                DevProofFixture.pairingValid(gimbalId, accountB, "inst-idem-b"));
        assertEquals(409, other.getResponse().getStatus());
        assertEquals("BOUND_TO_OTHER", errorOf(other).path("code").asText());
        assertEquals(accountA, bindingRow(gimbalId).get("bound_account_id"));

        // 同键同内容重放 → 200 + meta.replayed=true
        UUID replayGimbal = seedGimbal();
        String replayKey = "bind-replay-" + replayGimbal;
        String replayProof = DevProofFixture.pairingValid(replayGimbal, accountA, instA);
        MvcResult fresh = putBind(a.accessToken(), replayGimbal, replayKey, "0", replayProof);
        assertEquals(200, fresh.getResponse().getStatus());
        MvcResult replayed = putBind(a.accessToken(), replayGimbal, replayKey, "0", replayProof);
        assertEquals(200, replayed.getResponse().getStatus());
        assertTrue(bodyOf(replayed).path("meta").path("replayed").asBoolean());

        // 同键不同内容 → 409 IDEMPOTENCY_CONTENT_CONFLICT
        MvcResult conflict = putBind(a.accessToken(), replayGimbal, replayKey, "1", replayProof);
        assertEquals(409, conflict.getResponse().getStatus());
        assertEquals("IDEMPOTENCY_CONTENT_CONFLICT", errorOf(conflict).path("code").asText());
    }

    @Test
    @DisplayName("测试组 10：证明缺失/结构非法 400；验签失败/过期/别云台/别账号/nonce 重放 403；拒绝路径 T03 零变化")
    void pairingProofGuards() throws Exception {
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-proof-a");
        UUID accountA = UUID.fromString(a.accountId());
        String instA = "inst-proof-a";

        UUID missingGimbal = seedGimbal();
        MvcResult missing = putBind(a.accessToken(), missingGimbal, "p-missing-" + missingGimbal,
                "0", null);
        assertEquals(400, missing.getResponse().getStatus());
        assertUnboundAndUnchanged(missingGimbal);

        UUID malformedGimbal = seedGimbal();
        MvcResult malformed = putBind(a.accessToken(), malformedGimbal,
                "p-malformed-" + malformedGimbal, "0", DevProofFixture.malformedProof());
        assertEquals(400, malformed.getResponse().getStatus());
        assertUnboundAndUnchanged(malformedGimbal);

        assertRejectedGimbal(403, (g, acc, inst) ->
                DevProofFixture.pairingBadSignature(g, acc, inst));
        assertRejectedGimbal(403, DevProofFixture::pairingExpired);
        assertRejectedGimbal(403, (g, acc, inst) -> DevProofFixture.pairingWrongGimbal(acc, inst));
        assertRejectedGimbal(403, (g, acc, inst) -> DevProofFixture.pairingWrongAccount(g, inst));
        assertRejectedGimbal(403, DevProofFixture::pairingUnsupportedVersion);

        // nonce 重放：首次绑定成功（消耗 nonce），同 proof 新键再用 → 403，绑定保持
        UUID nonceGimbal = seedGimbal();
        String sharedProof = DevProofFixture.pairingValid(nonceGimbal, accountA, instA);
        MvcResult bound = putBind(a.accessToken(), nonceGimbal, "nonce-first-" + nonceGimbal, "0",
                sharedProof);
        assertEquals(200, bound.getResponse().getStatus(), bound.getResponse().getContentAsString());
        MvcResult replay = putBind(a.accessToken(), nonceGimbal, "nonce-second-" + nonceGimbal, "1",
                sharedProof);
        assertEquals(403, replay.getResponse().getStatus());
        assertEquals(accountA, bindingRow(nonceGimbal).get("bound_account_id"));
        assertEquals(1L, ((Number) bindingRow(nonceGimbal).get("binding_revision")).longValue());

        // 仅提交 gimbalId 不能建立绑定
        UUID idOnlyGimbal = seedGimbal();
        MvcResult idOnly = putBind(a.accessToken(), idOnlyGimbal, "p-idonly-" + idOnlyGimbal, "0",
                idOnlyGimbal.toString());
        assertEquals(400, idOnly.getResponse().getStatus());
        assertUnboundAndUnchanged(idOnlyGimbal);
    }

    private interface ProofFactory {
        String create(UUID gimbal, UUID account, String installationId);
    }

    private void assertRejectedGimbal(int status, ProofFactory factory) throws Exception {
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-proof-x");
        UUID accountA = UUID.fromString(a.accountId());
        UUID gimbal = seedGimbal();
        MvcResult result = putBind(a.accessToken(), gimbal, "p-" + gimbal, "0",
                factory.create(gimbal, accountA, "inst-proof-x"));
        assertEquals(status, result.getResponse().getStatus(),
                result.getResponse().getContentAsString());
        assertUnboundAndUnchanged(gimbal);
    }

    @Test
    @DisplayName("测试组 11：A07 三态、other 只两字段、缺头 400、非法证明 403、GET 零变化")
    void bindingStatusThreeStates() throws Exception {
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-status-a");
        LoginResult b = loginAppWithInstallation(newPhone(), "inst-status-b");
        UUID accountA = UUID.fromString(a.accountId());
        UUID accountB = UUID.fromString(b.accountId());

        UUID unbound = seedGimbal();
        MvcResult unboundView = getBindingStatus(a.accessToken(), unbound,
                DevProofFixture.pairingValid(unbound, accountA, "inst-status-a"));
        assertEquals(200, unboundView.getResponse().getStatus());
        assertEquals("unbound", dataOf(unboundView).path("bindingStatus").asText());
        assertEquals("0", dataOf(unboundView).path("bindingRevision").asText());

        UUID bound = seedGimbal();
        jdbc.update("UPDATE gimbals SET bound_account_id = ?, bound_at = now(),"
                + " binding_revision = 1 WHERE id = ?", accountA, bound);
        Map<String, Object> before = bindingRow(bound);

        MvcResult self = getBindingStatus(a.accessToken(), bound,
                DevProofFixture.pairingValid(bound, accountA, "inst-status-a"));
        assertEquals("self", dataOf(self).path("bindingStatus").asText());

        MvcResult other = getBindingStatus(b.accessToken(), bound,
                DevProofFixture.pairingValid(bound, accountB, "inst-status-b"));
        assertEquals(200, other.getResponse().getStatus());
        JsonNode otherData = dataOf(other);
        assertEquals("other", otherData.path("bindingStatus").asText());
        assertEquals("1", otherData.path("bindingRevision").asText());
        Set<String> names = new HashSet<>();
        otherData.fieldNames().forEachRemaining(names::add);
        assertEquals(Set.of("bindingStatus", "bindingRevision"), names);
        assertFalse(other.getResponse().getContentAsString().contains(accountA.toString()));

        // GET 零变化
        assertEquals(before, bindingRow(bound));

        // 缺 X-Pairing-Proof → 400
        assertEquals(400, getBindingStatus(a.accessToken(), bound, null).getResponse().getStatus());
        // 非法证明 → 403
        assertEquals(403, getBindingStatus(a.accessToken(), bound,
                DevProofFixture.malformedProof()).getResponse().getStatus());
        // 云台主体 → 403（不通过账号配网入口调用）
        GimbalSession gimbalSession = gimbalSession();
        MvcResult gimbalCaller = getBindingStatus(gimbalSession.accessToken(), gimbalSession.gimbalId(),
                DevProofFixture.pairingValid(gimbalSession.gimbalId(),
                        UUID.fromString(a.accountId()), "inst-status-a"));
        assertEquals(403, gimbalCaller.getResponse().getStatus());
    }

    @Test
    @DisplayName("测试组 12：解绑递增代次、幂等不递增、旧解绑不删新绑定、不触碰授权/报告/任务/微晶")
    void unbindSemantics() throws Exception {
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-unbind-a");
        LoginResult b = loginAppWithInstallation(newPhone(), "inst-unbind-b");
        UUID accountA = UUID.fromString(a.accountId());
        UUID accountB = UUID.fromString(b.accountId());
        UUID gimbal = seedGimbal();

        MvcResult bound = putBind(a.accessToken(), gimbal, "unbind-bind-" + gimbal, "0",
                DevProofFixture.pairingValid(gimbal, accountA, "inst-unbind-a"));
        assertEquals(200, bound.getResponse().getStatus(), bound.getResponse().getContentAsString());
        assertEquals(1L, ((Number) bindingRow(gimbal).get("binding_revision")).longValue());

        long grants = count("member_access_grants", "account_id = ?", accountA);
        long assessments = count("skin_assessments", "gimbal_id = ?", gimbal);
        long plans = count("care_plans", "1 = 1");
        long records = count("care_records", "1 = 1");
        long microcrystals = count("microcrystals", "serial_no LIKE 'gimbal-serial-%'");
        long executions = count("care_executions", "controller_gimbal_id = ?", gimbal);

        MvcResult unbound = deleteUnbind(a.accessToken(), gimbal, "unbind-real-" + gimbal,
                "\"binding-1\"");
        assertEquals(204, unbound.getResponse().getStatus(), unbound.getResponse().getContentAsString());
        Map<String, Object> afterUnbind = bindingRow(gimbal);
        assertNull(afterUnbind.get("bound_account_id"));
        assertNull(afterUnbind.get("bound_at"));
        assertEquals(2L, ((Number) afterUnbind.get("binding_revision")).longValue());

        // 同键重放 → 204，代次不再递增（走既有 replay 投影，不重做写入）
        assertEquals(204, deleteUnbind(a.accessToken(), gimbal, "unbind-real-" + gimbal,
                "\"binding-1\"").getResponse().getStatus());
        assertEquals(2L, ((Number) bindingRow(gimbal).get("binding_revision")).longValue());

        // 新键解绑"未绑定"云台 → 404 RESOURCE_NOT_VISIBLE（不再冒充"我解绑成功"），
        // 代次/绑定列逐列未变；且与不存在 UUID 的 404 掩蔽 requestId 后逐字节一致。
        Map<String, Object> afterReplay = bindingRow(gimbal);
        MvcResult unboundAgain = deleteUnbind(a.accessToken(), gimbal, "unbind-again-" + gimbal, null);
        MvcResult missingGimbal = deleteUnbind(a.accessToken(), UUID.randomUUID(),
                "unbind-missing-" + gimbal, null);
        assertEquals(404, unboundAgain.getResponse().getStatus(),
                unboundAgain.getResponse().getContentAsString());
        assertEquals("RESOURCE_NOT_VISIBLE", errorOf(unboundAgain).path("code").asText());
        assertIndistinguishableError(unboundAgain, missingGimbal);
        assertEquals(afterReplay, bindingRow(gimbal));
        assertEquals(2L, ((Number) bindingRow(gimbal).get("binding_revision")).longValue());
        String rawUnbound = unboundAgain.getResponse().getContentAsString();
        String rawMissing = missingGimbal.getResponse().getContentAsString();
        String idUnbound = bodyOf(unboundAgain).path("requestId").asText();
        String idMissing = bodyOf(missingGimbal).path("requestId").asText();
        assertEquals(rawUnbound.replace(idUnbound, "<requestId>"),
                rawMissing.replace(idMissing, "<requestId>"));

        // 同键重试这个新拒绝 → 重放同一 T13 rejected，仍 404 且逐列未变
        MvcResult rejectedReplay = deleteUnbind(a.accessToken(), gimbal,
                "unbind-again-" + gimbal, null);
        assertEquals(404, rejectedReplay.getResponse().getStatus());
        assertIndistinguishableError(unboundAgain, rejectedReplay);
        assertEquals(afterReplay, bindingRow(gimbal));

        // B 建立新绑定（expected=2）→ rev3；A 的旧解绑（旧 If-Match）→ 409，B 绑定完好
        MvcResult rebound = putBind(b.accessToken(), gimbal, "unbind-b-" + gimbal, "2",
                DevProofFixture.pairingValid(gimbal, accountB, "inst-unbind-b"));
        assertEquals(200, rebound.getResponse().getStatus(), rebound.getResponse().getContentAsString());
        assertEquals(3L, ((Number) bindingRow(gimbal).get("binding_revision")).longValue());

        MvcResult stale = deleteUnbind(a.accessToken(), gimbal, "unbind-stale-" + gimbal,
                "\"binding-1\"");
        assertEquals(409, stale.getResponse().getStatus());
        assertEquals("BINDING_CHANGED", errorOf(stale).path("code").asText());
        assertEquals(accountB, bindingRow(gimbal).get("bound_account_id"));
        assertEquals(3L, ((Number) bindingRow(gimbal).get("binding_revision")).longValue());

        // A 无 If-Match 解绑 B 的绑定 → 404，B 绑定完好
        MvcResult foreign = deleteUnbind(a.accessToken(), gimbal, "unbind-foreign-" + gimbal, null);
        assertEquals(404, foreign.getResponse().getStatus());
        assertEquals(accountB, bindingRow(gimbal).get("bound_account_id"));

        // 解绑不撤销授权/不删报告方案记录/不改当前任务/不动微晶
        assertEquals(grants, count("member_access_grants", "account_id = ?", accountA));
        assertEquals(assessments, count("skin_assessments", "gimbal_id = ?", gimbal));
        assertEquals(plans, count("care_plans", "1 = 1"));
        assertEquals(records, count("care_records", "1 = 1"));
        assertEquals(microcrystals, count("microcrystals", "serial_no LIKE 'gimbal-serial-%'"));
        assertEquals(executions, count("care_executions", "controller_gimbal_id = ?", gimbal));
        Map<String, Object> finalRow = bindingRow(gimbal);
        assertNull(finalRow.get("current_assessment_id"));
        assertEquals(0L, ((Number) finalRow.get("current_assessment_revision")).longValue());
    }

    @Test
    @DisplayName("Oracle#3：未绑定在任何 If-Match 下统一 404 不可区分；本人绑定+陈旧 If-Match 仍 409")
    void unboundUnbindIsInvisibleRegardlessOfIfMatch() throws Exception {
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-ub-inv-a");
        UUID accountA = UUID.fromString(a.accountId());

        // 本人绑定 + 陈旧 If-Match → 409（保持；这是自己的绑定，不构成存在性泄漏）
        UUID mine = seedGimbal();
        assertEquals(200, putBind(a.accessToken(), mine, "ub-inv-mine",
                        "0", DevProofFixture.pairingValid(mine, accountA, "inst-ub-inv-a"))
                .getResponse().getStatus());
        MvcResult myStale = deleteUnbind(a.accessToken(), mine, "ub-inv-mine-stale", "\"binding-0\"");
        assertEquals(409, myStale.getResponse().getStatus());
        assertEquals("BINDING_CHANGED", errorOf(myStale).path("code").asText());
        assertEquals(1L, ((Number) bindingRow(mine).get("binding_revision")).longValue());
        assertNotNull(bindingRow(mine).get("bound_account_id"));

        // 绑定→解绑，使云台进入"未绑定且 binding_revision=2"
        UUID unbound = seedGimbal();
        assertEquals(200, putBind(a.accessToken(), unbound, "ub-inv-bind",
                        "0", DevProofFixture.pairingValid(unbound, accountA, "inst-ub-inv-a"))
                .getResponse().getStatus());
        assertEquals(204, deleteUnbind(a.accessToken(), unbound, "ub-inv-unbind",
                "\"binding-1\"").getResponse().getStatus());
        Map<String, Object> before = bindingRow(unbound);
        assertEquals(2L, ((Number) before.get("binding_revision")).longValue());
        assertNull(before.get("bound_account_id"));

        MvcResult missing = deleteUnbind(a.accessToken(), UUID.randomUUID(), "ub-inv-missing", null);
        // 未绑定 + 陈旧 If-Match（当前 rev=2，If-Match binding-1）
        MvcResult stale = deleteUnbind(a.accessToken(), unbound, "ub-inv-stale", "\"binding-1\"");
        // 未绑定 + 相符 If-Match（binding-2）
        MvcResult match = deleteUnbind(a.accessToken(), unbound, "ub-inv-match", "\"binding-2\"");
        // 未绑定 + 无 If-Match
        MvcResult none = deleteUnbind(a.accessToken(), unbound, "ub-inv-none", null);

        for (MvcResult r : List.of(stale, match, none)) {
            assertEquals(404, r.getResponse().getStatus(), r.getResponse().getContentAsString());
            assertEquals("RESOURCE_NOT_VISIBLE", errorOf(r).path("code").asText());
            assertEquals("gimbal not visible", errorOf(r).path("message").asText());
        }
        // 三者与不存在 UUID 的 404 掩蔽 requestId 后逐字节一致
        String rawMissing = missing.getResponse().getContentAsString();
        String idMissing = bodyOf(missing).path("requestId").asText();
        for (MvcResult r : List.of(stale, match, none)) {
            String raw = r.getResponse().getContentAsString();
            String id = bodyOf(r).path("requestId").asText();
            assertEquals(raw.replace(id, "<requestId>"),
                    rawMissing.replace(idMissing, "<requestId>"));
        }
        // 三个 404 均零写：绑定列/代次逐列未变
        assertEquals(before, bindingRow(unbound));
    }

    @Test
    @DisplayName("测试组 14：绑定云台 ≠ 成员资料授权")
    void bindingDoesNotGrantMemberAccess() throws Exception {
        LoginResult a = loginAppWithInstallation(newPhone(), "inst-sc05-a");
        UUID accountA = UUID.fromString(a.accountId());
        UUID gimbal = seedGimbal();
        MvcResult bound = putBind(a.accessToken(), gimbal, "sc05-" + gimbal, "0",
                DevProofFixture.pairingValid(gimbal, accountA, "inst-sc05-a"));
        assertEquals(200, bound.getResponse().getStatus());
        assertEquals(0, count("member_access_grants", "account_id = ?", accountA));
    }
}

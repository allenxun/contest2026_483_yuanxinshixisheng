package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import cn.yuanxin.mvp.web.testdouble.FaceProviderDouble;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
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
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * M1（身份与查看授权）真实 PG 集成测试：M1-A01/A02/A03 成功、无效主体、
 * 幂等重放、撤销防复活、分页与并发竞争。
 *
 * <p>覆盖 lane-m1.md 的 12 个必测用例（用例 6 存储失败见
 * {@link MemberAccessGrantStorageFailureIT}）。</p>
 */
class MemberAccessGrantsIT extends AbstractWebIT {

    private static final byte[] PNG_HEADER = {
            (byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    private static final String CAPTURED_AT = "2026-09-11T10:00:00Z";

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    FaceIdentityResolver faceIdentityResolver;

    @Autowired
    FaceProvider faceProvider;

    @AfterEach
    void resetFaceDouble() {
        ((FaceProviderDouble) faceProvider).setClassification(FaceClassification.MATCHED);
    }

    // ---------------- helpers ----------------

    private static byte[] faceBytes(String tag) {
        byte[] body = tag.getBytes(StandardCharsets.UTF_8);
        byte[] out = new byte[PNG_HEADER.length + body.length];
        System.arraycopy(PNG_HEADER, 0, out, 0, PNG_HEADER.length);
        System.arraycopy(body, 0, out, PNG_HEADER.length, body.length);
        return out;
    }

    private UUID seedMember(byte[] face) {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO members (id, identity_namespace, face_subject_ref) VALUES (?, ?, ?)",
                id, faceIdentityResolver.identityNamespace(),
                DevTestFaceIdentityResolver.subjectRefFor(face));
        return id;
    }

    private MockMultipartFile metadataPart(String captureId, String consentRef) {
        return metadataPart(captureId, consentRef, "grant", "");
    }

    private MockMultipartFile metadataPart(String captureId, String consentRef, String purpose,
                                           String extraJson) {
        String json = "{\"capture\":{\"captureId\":\"" + captureId + "\",\"capturedAt\":\""
                + CAPTURED_AT + "\",\"clientContinuityId\":\"cont-" + captureId
                + "\",\"purpose\":\"" + purpose + "\"}," + "\"consentEvidenceRef\":\"" + consentRef
                + "\"" + extraJson + "}";
        return new MockMultipartFile("metadata", "metadata", "application/json",
                json.getBytes(StandardCharsets.UTF_8));
    }

    private MvcResult postGrant(String token, String key, byte[] face, MockMultipartFile metadata)
            throws Exception {
        return mockMvc.perform(multipart("/api/v1/member-access-grants")
                        .file(metadata)
                        .file(new MockMultipartFile("face", "face.png", "image/png", face))
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key))
                .andReturn();
    }

    private MvcResult deleteGrant(String token, UUID grantId, String key) throws Exception {
        return mockMvc.perform(delete("/api/v1/me/member-access-grants/" + grantId)
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key))
                .andReturn();
    }

    private static JsonNode body(MvcResult result) throws Exception {
        return JSON.readTree(result.getResponse().getContentAsString());
    }

    private static String errorCode(MvcResult result) throws Exception {
        return body(result).path("error").path("code").asText();
    }

    private long totalRowsFor(UUID accountId, UUID memberId) {
        Integer c = jdbc.queryForObject("SELECT count(*) FROM member_access_grants"
                + " WHERE account_id = ? AND member_id = ?", Integer.class, accountId, memberId);
        return c == null ? 0 : c;
    }

    private long activeRowsFor(UUID accountId, UUID memberId) {
        Integer c = jdbc.queryForObject("SELECT count(*) FROM member_access_grants"
                + " WHERE account_id = ? AND member_id = ? AND status = 'active'",
                Integer.class, accountId, memberId);
        return c == null ? 0 : c;
    }

    private int memberCount() {
        Integer c = jdbc.queryForObject("SELECT count(*) FROM members", Integer.class);
        return c == null ? 0 : c;
    }

    private UUID t13Id(String operation, String key) {
        return jdbc.queryForObject("SELECT id FROM idempotency_requests"
                + " WHERE operation = ? AND idempotency_key = ?", UUID.class, operation, key);
    }

    private LoginResult loginAndAccount() throws Exception {
        return loginAppWithInstallation(newPhone(), "inst-" + UUID.randomUUID().toString().substring(0, 8));
    }

    private String issueGimbalToken() throws Exception {
        String serial = "SN-ID-" + UUID.randomUUID().toString().substring(0, 8);
        String authRef = "authref-" + serial;
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                + " VALUES (?::uuid, ?, ?, 3)", UUID.randomUUID().toString(), serial, authRef);
        MvcResult r = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + authRef
                                + "\",\"credentialVersion\":\"3\",\"proof\":\"p\"}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        return body(r).path("data").path("sessionToken").asText();
    }

    // ---------------- case 1 ----------------

    @Test
    @DisplayName("case1: 可靠匹配 → 201；T02/T11 落库与 verification_summary 不外泄")
    void reliableMatchCreatesGrant() throws Exception {
        LoginResult account = loginAndAccount();
        UUID accountId = UUID.fromString(account.accountId());
        byte[] face = faceBytes("case1-" + UUID.randomUUID());
        UUID memberId = seedMember(face);
        String key = "k-" + UUID.randomUUID();

        MvcResult r = postGrant(account.accessToken(), key, face, metadataPart("cap-1", "consent-1"));
        assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        assertNotNull(r.getResponse().getHeader("X-Request-Id"));

        JsonNode data = body(r).path("data");
        UUID grantId = UUID.fromString(data.path("grantId").asText());
        assertEquals(memberId.toString(), data.path("memberId").asText());
        assertEquals("active", data.path("status").asText());
        assertNotNull(data.path("grantedAt").asText(null));
        assertFalse(body(r).path("meta").path("replayed").asBoolean());

        String raw = r.getResponse().getContentAsString();
        assertFalse(raw.contains("verification_summary"), "internal summary leaked");
        assertFalse(raw.contains("classification"), "internal classification leaked");
        assertFalse(raw.contains("consentEvidenceRef"), "consent ref leaked");
        assertFalse(raw.contains("face_subject_ref"), "subject ref leaked");

        UUID t13 = t13Id(MemberAccessGrantService.OP_CREATE, key);
        var grant = jdbc.queryForMap("SELECT status, source_request_id, member_summary::text AS ms,"
                + " verification_summary::text AS vs FROM member_access_grants WHERE id = ?", grantId);
        assertEquals("active", grant.get("status"));
        assertEquals(t13, grant.get("source_request_id"));
        assertEquals("{}", grant.get("ms"));
        assertTrue(((String) grant.get("vs")).contains("schema_version"), (String) grant.get("vs"));
        Integer schemaVersion = jdbc.queryForObject("SELECT (verification_summary->>'schema_version')::int"
                + " FROM member_access_grants WHERE id = ?", Integer.class, grantId);
        assertEquals(1, schemaVersion);

        var media = jdbc.queryForList("SELECT purpose, state, member_id, uploader_type, uploader_ref"
                + " FROM media_objects WHERE request_id = ?", t13);
        assertEquals(1, media.size(), "exactly one face media row");
        assertEquals("grant_face", media.get(0).get("purpose"));
        assertEquals("available", media.get(0).get("state"));
        assertEquals(memberId, media.get(0).get("member_id"));
        assertEquals("app", media.get(0).get("uploader_type"));
        String uploaderRef = (String) media.get(0).get("uploader_ref");
        assertNotNull(uploaderRef);
        assertTrue(uploaderRef.startsWith(accountId + ":"), uploaderRef);
    }

    // ---------------- case 2 ----------------

    @Test
    @DisplayName("case2: 同账号同成员新键再次授权 → 200 同一 grantId，仅 1 行 active")
    void existingActiveGrantReused() throws Exception {
        LoginResult account = loginAndAccount();
        UUID accountId = UUID.fromString(account.accountId());
        byte[] face = faceBytes("case2-" + UUID.randomUUID());
        UUID memberId = seedMember(face);

        MvcResult first = postGrant(account.accessToken(), "k1-" + UUID.randomUUID(), face,
                metadataPart("cap-2a", "consent-2a"));
        assertEquals(201, first.getResponse().getStatus(), first.getResponse().getContentAsString());
        UUID grantId = UUID.fromString(body(first).path("data").path("grantId").asText());

        MvcResult second = postGrant(account.accessToken(), "k2-" + UUID.randomUUID(), face,
                metadataPart("cap-2b", "consent-2b"));
        assertEquals(200, second.getResponse().getStatus(), second.getResponse().getContentAsString());
        assertEquals(grantId, UUID.fromString(body(second).path("data").path("grantId").asText()));
        assertFalse(body(second).path("meta").path("replayed").asBoolean());

        assertEquals(1, activeRowsFor(accountId, memberId));
        assertEquals(1, totalRowsFor(accountId, memberId));
    }

    // ---------------- case 3 ----------------

    @Test
    @DisplayName("case3: 同键同内容重放 → 200 replayed；同键不同内容 → 409")
    void replayAndContentConflict() throws Exception {
        LoginResult account = loginAndAccount();
        byte[] face = faceBytes("case3-" + UUID.randomUUID());
        UUID memberId = seedMember(face);
        String key = "k-" + UUID.randomUUID();

        MvcResult first = postGrant(account.accessToken(), key, face, metadataPart("cap-3", "consent-3"));
        assertEquals(201, first.getResponse().getStatus(), first.getResponse().getContentAsString());
        UUID grantId = UUID.fromString(body(first).path("data").path("grantId").asText());

        MvcResult replay = postGrant(account.accessToken(), key, face, metadataPart("cap-3", "consent-3"));
        assertEquals(200, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        assertTrue(body(replay).path("meta").path("replayed").asBoolean());
        assertEquals(grantId, UUID.fromString(body(replay).path("data").path("grantId").asText()));
        assertEquals(1, totalRowsFor(UUID.fromString(account.accountId()), memberId));

        MvcResult conflict = postGrant(account.accessToken(), key, face,
                metadataPart("cap-3", "consent-other"));
        assertEquals(409, conflict.getResponse().getStatus(), conflict.getResponse().getContentAsString());
        assertEquals("IDEMPOTENCY_CONTENT_CONFLICT", errorCode(conflict));
    }

    // ---------------- case 4 ----------------

    @Test
    @DisplayName("case4: 无匹配/不确定 → 403 FACE_NOT_VERIFIED，T02 与 members 零新行")
    void noReliableMatchIsFaceNotVerified() throws Exception {
        LoginResult account = loginAndAccount();
        UUID accountId = UUID.fromString(account.accountId());
        int membersBefore = memberCount();

        // MATCHED but no enrolled member for this image → indistinguishable 403.
        MvcResult noMember = postGrant(account.accessToken(), "k-" + UUID.randomUUID(),
                faceBytes("case4-absent-" + UUID.randomUUID()), metadataPart("cap-4a", "consent-4a"));
        assertEquals(403, noMember.getResponse().getStatus(), noMember.getResponse().getContentAsString());
        assertEquals("FACE_NOT_VERIFIED", errorCode(noMember));
        assertFalse(noMember.getResponse().getContentAsString().contains("candidate"));

        // UNCERTAIN classification.
        ((FaceProviderDouble) faceProvider).setClassification(FaceClassification.UNCERTAIN);
        MvcResult uncertain = postGrant(account.accessToken(), "k-" + UUID.randomUUID(),
                faceBytes("case4-uncertain-" + UUID.randomUUID()), metadataPart("cap-4b", "consent-4b"));
        assertEquals(403, uncertain.getResponse().getStatus(), uncertain.getResponse().getContentAsString());
        assertEquals("FACE_NOT_VERIFIED", errorCode(uncertain));

        Integer grants = jdbc.queryForObject("SELECT count(*) FROM member_access_grants"
                + " WHERE account_id = ?", Integer.class, accountId);
        assertEquals(0, grants);
        assertEquals(membersBefore, memberCount(), "M1-A01 must never create members");
    }

    // ---------------- case 5 ----------------

    @Test
    @DisplayName("case5: 校验失败 400/413/415/422 且无 T02 行")
    void validationFailures() throws Exception {
        LoginResult account = loginAndAccount();
        UUID accountId = UUID.fromString(account.accountId());
        byte[] face = faceBytes("case5-" + UUID.randomUUID());

        // missing Idempotency-Key
        MvcResult noKey = mockMvc.perform(multipart("/api/v1/member-access-grants")
                        .file(metadataPart("cap-5", "consent-5"))
                        .file(new MockMultipartFile("face", "face.png", "image/png", face))
                        .header("Authorization", "Bearer " + account.accessToken()))
                .andReturn();
        assertEquals(400, noKey.getResponse().getStatus());
        assertEquals("INVALID_INPUT", errorCode(noKey));

        // unknown field memberId
        MvcResult withMemberId = postGrant(account.accessToken(), "k-" + UUID.randomUUID(), face,
                metadataPart("cap-5", "consent-5", "grant", ",\"memberId\":\"" + UUID.randomUUID() + "\""));
        assertEquals(400, withMemberId.getResponse().getStatus(), withMemberId.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", errorCode(withMemberId));

        // missing consentEvidenceRef (extra param strip -> construct raw without consent)
        MockMultipartFile missingConsent = new MockMultipartFile("metadata", "metadata",
                "application/json",
                ("{\"capture\":{\"captureId\":\"cap-5\",\"capturedAt\":\"" + CAPTURED_AT
                        + "\",\"clientContinuityId\":\"cont-5\",\"purpose\":\"grant\"}}")
                        .getBytes(StandardCharsets.UTF_8));
        MvcResult noConsent = postGrant(account.accessToken(), "k-" + UUID.randomUUID(), face,
                missingConsent);
        assertEquals(400, noConsent.getResponse().getStatus());
        assertEquals("INVALID_INPUT", errorCode(noConsent));

        // purpose != grant
        MvcResult wrongPurpose = postGrant(account.accessToken(), "k-" + UUID.randomUUID(), face,
                metadataPart("cap-5", "consent-5", "admission", ""));
        assertEquals(400, wrongPurpose.getResponse().getStatus());
        assertEquals("INVALID_INPUT", errorCode(wrongPurpose));

        // non-image bytes
        MvcResult notImage = postGrant(account.accessToken(), "k-" + UUID.randomUUID(),
                "not-an-image".getBytes(StandardCharsets.UTF_8), metadataPart("cap-5", "consent-5"));
        assertEquals(415, notImage.getResponse().getStatus(), notImage.getResponse().getContentAsString());
        assertEquals("UNSUPPORTED_IMAGE", errorCode(notImage));

        // oversized (>10MiB)
        byte[] huge = new byte[10 * 1024 * 1024 + 1];
        System.arraycopy(PNG_HEADER, 0, huge, 0, PNG_HEADER.length);
        MvcResult tooLarge = postGrant(account.accessToken(), "k-" + UUID.randomUUID(), huge,
                metadataPart("cap-5", "consent-5"));
        assertEquals(413, tooLarge.getResponse().getStatus(), tooLarge.getResponse().getContentAsString());
        assertEquals("UPLOAD_TOO_LARGE", errorCode(tooLarge));

        // quality rejected
        ((FaceProviderDouble) faceProvider).setClassification(FaceClassification.QUALITY_REJECTED);
        MvcResult quality = postGrant(account.accessToken(), "k-" + UUID.randomUUID(), face,
                metadataPart("cap-5", "consent-5"));
        assertEquals(422, quality.getResponse().getStatus(), quality.getResponse().getContentAsString());
        assertEquals("FACE_QUALITY_REJECTED", errorCode(quality));

        Integer grants = jdbc.queryForObject("SELECT count(*) FROM member_access_grants"
                + " WHERE account_id = ?", Integer.class, accountId);
        assertEquals(0, grants);
    }

    // ---------------- case 7 ----------------

    @Test
    @DisplayName("case7: 云台主体 → 403 CALLER_NOT_ALLOWED；无 token → 401")
    void callerTypeEnforcement() throws Exception {
        String gimbalToken = issueGimbalToken();
        byte[] face = faceBytes("case7-" + UUID.randomUUID());

        MvcResult create = postGrant(gimbalToken, "k-" + UUID.randomUUID(), face,
                metadataPart("cap-7", "consent-7"));
        assertEquals(403, create.getResponse().getStatus(), create.getResponse().getContentAsString());
        assertEquals("CALLER_NOT_ALLOWED", errorCode(create));

        MvcResult list = mockMvc.perform(get("/api/v1/me/member-access-grants")
                        .header("Authorization", "Bearer " + gimbalToken))
                .andReturn();
        assertEquals(403, list.getResponse().getStatus());
        assertEquals("CALLER_NOT_ALLOWED", errorCode(list));

        MvcResult revoke = deleteGrant(gimbalToken, UUID.randomUUID(), "k-" + UUID.randomUUID());
        assertEquals(403, revoke.getResponse().getStatus());
        assertEquals("CALLER_NOT_ALLOWED", errorCode(revoke));

        MvcResult anonymous = mockMvc.perform(get("/api/v1/me/member-access-grants")).andReturn();
        assertEquals(401, anonymous.getResponse().getStatus());
        assertEquals("AUTH_REQUIRED", errorCode(anonymous));
    }

    // ---------------- case 8 ----------------

    @Test
    @DisplayName("case8: A02 仅 active、分页游标、非法 cursor 400、跨账号隔离")
    void listOnlyActiveWithPagination() throws Exception {
        LoginResult account = loginAndAccount();
        UUID accountId = UUID.fromString(account.accountId());
        List<UUID> grantIds = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            byte[] face = faceBytes("case8-" + i + "-" + UUID.randomUUID());
            seedMember(face);
            MvcResult r = postGrant(account.accessToken(), "k-" + UUID.randomUUID(), face,
                    metadataPart("cap-8-" + i, "consent-8-" + i));
            assertEquals(201, r.getResponse().getStatus(), r.getResponse().getContentAsString());
            grantIds.add(UUID.fromString(body(r).path("data").path("grantId").asText()));
        }

        MvcResult page1 = mockMvc.perform(get("/api/v1/me/member-access-grants")
                        .param("limit", "2")
                        .header("Authorization", "Bearer " + account.accessToken()))
                .andReturn();
        assertEquals(200, page1.getResponse().getStatus(), page1.getResponse().getContentAsString());
        assertEquals(2, body(page1).path("data").path("items").size());
        String cursor = body(page1).path("data").path("nextCursor").asText();
        assertFalse(cursor.isBlank());

        MvcResult page2 = mockMvc.perform(get("/api/v1/me/member-access-grants")
                        .param("limit", "2").param("cursor", cursor)
                        .header("Authorization", "Bearer " + account.accessToken()))
                .andReturn();
        assertEquals(200, page2.getResponse().getStatus(), page2.getResponse().getContentAsString());
        assertEquals(1, body(page2).path("data").path("items").size());
        assertTrue(body(page2).path("data").path("nextCursor").isNull());

        Set<String> union = new HashSet<>();
        body(page1).path("data").path("items").forEach(n -> union.add(n.path("grantId").asText()));
        body(page2).path("data").path("items").forEach(n -> union.add(n.path("grantId").asText()));
        assertEquals(3, union.size(), union.toString());
        for (UUID id : grantIds) {
            assertTrue(union.contains(id.toString()));
        }

        // revoke one → disappears immediately from active-only list
        UUID revoked = grantIds.get(0);
        assertEquals(204, deleteGrant(account.accessToken(), revoked, "k-" + UUID.randomUUID())
                .getResponse().getStatus());
        MvcResult all = mockMvc.perform(get("/api/v1/me/member-access-grants")
                        .param("limit", "100")
                        .header("Authorization", "Bearer " + account.accessToken()))
                .andReturn();
        assertEquals(2, body(all).path("data").path("items").size());
        body(all).path("data").path("items").forEach(n ->
                assertNotEquals(revoked.toString(), n.path("grantId").asText()));

        // cross-account isolation
        LoginResult other = loginAndAccount();
        byte[] otherFace = faceBytes("case8-other-" + UUID.randomUUID());
        seedMember(otherFace);
        MvcResult otherGrant = postGrant(other.accessToken(), "k-" + UUID.randomUUID(), otherFace,
                metadataPart("cap-8-other", "consent-8-other"));
        String otherGrantId = body(otherGrant).path("data").path("grantId").asText();
        MvcResult mine = mockMvc.perform(get("/api/v1/me/member-access-grants")
                        .param("limit", "100")
                        .header("Authorization", "Bearer " + account.accessToken()))
                .andReturn();
        body(mine).path("data").path("items").forEach(n ->
                assertNotEquals(otherGrantId, n.path("grantId").asText()));
        assertEquals(2, body(mine).path("data").path("items").size());

        // empty account
        LoginResult emptyAccount = loginAndAccount();
        MvcResult empty = mockMvc.perform(get("/api/v1/me/member-access-grants")
                        .header("Authorization", "Bearer " + emptyAccount.accessToken()))
                .andReturn();
        assertEquals(0, body(empty).path("data").path("items").size());
        assertTrue(body(empty).path("data").path("nextCursor").isNull());

        // illegal cursor / limit
        MvcResult badCursor = mockMvc.perform(get("/api/v1/me/member-access-grants")
                        .param("cursor", "!!!not-base64!!!")
                        .header("Authorization", "Bearer " + account.accessToken()))
                .andReturn();
        assertEquals(400, badCursor.getResponse().getStatus());
        assertEquals("INVALID_INPUT", errorCode(badCursor));

        for (String badLimit : List.of("0", "101")) {
            MvcResult r = mockMvc.perform(get("/api/v1/me/member-access-grants")
                            .param("limit", badLimit)
                            .header("Authorization", "Bearer " + account.accessToken()))
                    .andReturn();
            assertEquals(400, r.getResponse().getStatus(), "limit=" + badLimit);
        }
    }

    // ---------------- case 9 ----------------

    @Test
    @DisplayName("case9: A03 撤销 204、重复撤销不刷新 revoked_at、他人/不存在 404 不可区分")
    void revokeAndRepeat() throws Exception {
        LoginResult account = loginAndAccount();
        byte[] face = faceBytes("case9-" + UUID.randomUUID());
        seedMember(face);
        MvcResult created = postGrant(account.accessToken(), "k-" + UUID.randomUUID(), face,
                metadataPart("cap-9", "consent-9"));
        UUID grantId = UUID.fromString(body(created).path("data").path("grantId").asText());

        MvcResult revoke = deleteGrant(account.accessToken(), grantId, "kd-1-" + UUID.randomUUID());
        assertEquals(204, revoke.getResponse().getStatus(), revoke.getResponse().getContentAsString());
        assertEquals("", revoke.getResponse().getContentAsString());
        assertNotNull(revoke.getResponse().getHeader("X-Request-Id"));

        String status = jdbc.queryForObject("SELECT status FROM member_access_grants WHERE id = ?",
                String.class, grantId);
        assertEquals("revoked", status);
        Timestamp firstRevokedAt = jdbc.queryForObject(
                "SELECT revoked_at FROM member_access_grants WHERE id = ?", Timestamp.class, grantId);
        assertNotNull(firstRevokedAt);

        // repeat with SAME key (T13 replay) and with NEW key: both 204, revoked_at unchanged
        String sameKey = jdbc.queryForObject("SELECT idempotency_key FROM idempotency_requests"
                + " WHERE operation = ? AND resource_id = ?", String.class,
                MemberAccessGrantService.OP_REVOKE, grantId);
        assertEquals(204, deleteGrant(account.accessToken(), grantId, sameKey).getResponse().getStatus());
        assertEquals(204, deleteGrant(account.accessToken(), grantId, "kd-2-" + UUID.randomUUID())
                .getResponse().getStatus());
        Timestamp afterRepeats = jdbc.queryForObject(
                "SELECT revoked_at FROM member_access_grants WHERE id = ?", Timestamp.class, grantId);
        assertEquals(firstRevokedAt, afterRepeats, "revoked_at must not be refreshed");

        // other account cannot revoke
        LoginResult other = loginAndAccount();
        MvcResult foreign = deleteGrant(other.accessToken(), grantId, "kf-" + UUID.randomUUID());
        assertEquals(404, foreign.getResponse().getStatus());
        MvcResult missing = deleteGrant(other.accessToken(), UUID.randomUUID(), "km-" + UUID.randomUUID());
        assertEquals(404, missing.getResponse().getStatus());
        assertEquals("RESOURCE_NOT_VISIBLE", errorCode(foreign));
        assertEquals("RESOURCE_NOT_VISIBLE", errorCode(missing));

        // byte-identical error body after masking the per-attempt requestId
        String rawForeign = foreign.getResponse().getContentAsString();
        String rawMissing = missing.getResponse().getContentAsString();
        String idForeign = body(foreign).path("requestId").asText();
        String idMissing = body(missing).path("requestId").asText();
        assertNotEquals(idForeign, idMissing);
        assertEquals(rawForeign.replace(idForeign, "<requestId>"),
                rawMissing.replace(idMissing, "<requestId>"));

        // still active-untouched
        assertEquals("revoked", jdbc.queryForObject(
                "SELECT status FROM member_access_grants WHERE id = ?", String.class, grantId));

        // invalid grantId UUID → 400 INVALID_INPUT
        MvcResult badId = mockMvc.perform(delete("/api/v1/me/member-access-grants/not-a-uuid")
                        .header("Authorization", "Bearer " + account.accessToken())
                        .header("Idempotency-Key", "kb-" + UUID.randomUUID()))
                .andReturn();
        assertEquals(400, badId.getResponse().getStatus(), badId.getResponse().getContentAsString());
        assertEquals("INVALID_INPUT", errorCode(badId));
    }

    // ---------------- case 10 ----------------

    @Test
    @DisplayName("case10: 撤销后原键重放 → 403 GRANT_REVOKED 不复活；新键新核验 → 新行")
    void revokedGrantIsNeverResurrected() throws Exception {
        LoginResult account = loginAndAccount();
        UUID accountId = UUID.fromString(account.accountId());
        byte[] face = faceBytes("case10-" + UUID.randomUUID());
        UUID memberId = seedMember(face);
        String createKey = "kc-" + UUID.randomUUID();

        MvcResult created = postGrant(account.accessToken(), createKey, face, metadataPart("cap-10", "consent-10"));
        UUID oldGrant = UUID.fromString(body(created).path("data").path("grantId").asText());
        assertEquals(204, deleteGrant(account.accessToken(), oldGrant, "kd-" + UUID.randomUUID())
                .getResponse().getStatus());

        // replay the original A01 key + identical content
        MvcResult replay = postGrant(account.accessToken(), createKey, face, metadataPart("cap-10", "consent-10"));
        assertEquals(403, replay.getResponse().getStatus(), replay.getResponse().getContentAsString());
        assertEquals("GRANT_REVOKED", errorCode(replay));
        assertEquals(0, activeRowsFor(accountId, memberId));
        assertEquals(1, totalRowsFor(accountId, memberId), "no new row on replay");

        // fresh key → full verification → NEW grant row
        MvcResult fresh = postGrant(account.accessToken(), "kn-" + UUID.randomUUID(), face,
                metadataPart("cap-10b", "consent-10b"));
        assertEquals(201, fresh.getResponse().getStatus(), fresh.getResponse().getContentAsString());
        UUID newGrant = UUID.fromString(body(fresh).path("data").path("grantId").asText());
        assertNotEquals(oldGrant, newGrant);
        assertEquals(1, activeRowsFor(accountId, memberId));
        assertEquals(2, totalRowsFor(accountId, memberId));
        assertEquals("revoked", jdbc.queryForObject(
                "SELECT status FROM member_access_grants WHERE id = ?", String.class, oldGrant));
    }

    // ---------------- case 11 ----------------

    @Test
    @DisplayName("case11: 并发不同键 → 恰好 1 行 active，无 500/唯一索引外泄")
    void concurrentCreatesYieldExactlyOneActive() throws Exception {
        LoginResult account = loginAndAccount();
        UUID accountId = UUID.fromString(account.accountId());
        byte[] face = faceBytes("case11-" + UUID.randomUUID());
        UUID memberId = seedMember(face);
        MockMultipartFile m1 = metadataPart("cap-11a", "consent-11a");
        MockMultipartFile m2 = metadataPart("cap-11b", "consent-11b");

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);
        try {
            Callable<Integer> first = () -> {
                ready.countDown();
                go.await(10, TimeUnit.SECONDS);
                return postGrant(account.accessToken(), "k11a-" + UUID.randomUUID(), face, m1)
                        .getResponse().getStatus();
            };
            Callable<Integer> second = () -> {
                ready.countDown();
                go.await(10, TimeUnit.SECONDS);
                return postGrant(account.accessToken(), "k11b-" + UUID.randomUUID(), face, m2)
                        .getResponse().getStatus();
            };
            Future<Integer> f1 = pool.submit(first);
            Future<Integer> f2 = pool.submit(second);
            assertTrue(ready.await(10, TimeUnit.SECONDS));
            go.countDown();
            int s1 = f1.get(30, TimeUnit.SECONDS);
            int s2 = f2.get(30, TimeUnit.SECONDS);

            assertEquals(Set.of(200, 201), Set.of(s1, s2), "statuses " + s1 + "/" + s2);
            assertEquals(1, activeRowsFor(accountId, memberId));
        } finally {
            pool.shutdownNow();
        }
    }

    // ---------------- case 12 ----------------

    @Test
    @DisplayName("case12: A 撤销不影响 B 对同一成员的 active 关系")
    void revokeDoesNotAffectOtherAccounts() throws Exception {
        LoginResult a = loginAndAccount();
        LoginResult b = loginAndAccount();
        byte[] face = faceBytes("case12-" + UUID.randomUUID());
        UUID memberId = seedMember(face);

        MvcResult grantA = postGrant(a.accessToken(), "ka-" + UUID.randomUUID(), face,
                metadataPart("cap-12a", "consent-12a"));
        UUID idA = UUID.fromString(body(grantA).path("data").path("grantId").asText());
        MvcResult grantB = postGrant(b.accessToken(), "kb-" + UUID.randomUUID(), face,
                metadataPart("cap-12b", "consent-12b"));
        UUID idB = UUID.fromString(body(grantB).path("data").path("grantId").asText());

        assertEquals(204, deleteGrant(a.accessToken(), idA, "kda-" + UUID.randomUUID())
                .getResponse().getStatus());

        assertEquals("active", jdbc.queryForObject(
                "SELECT status FROM member_access_grants WHERE id = ?", String.class, idB));
        assertEquals(1, activeRowsFor(UUID.fromString(b.accountId()), memberId));
        MvcResult listB = mockMvc.perform(get("/api/v1/me/member-access-grants")
                        .header("Authorization", "Bearer " + b.accessToken()))
                .andReturn();
        List<String> ids = new ArrayList<>();
        body(listB).path("data").path("items").forEach(n -> ids.add(n.path("grantId").asText()));
        assertTrue(ids.contains(idB.toString()));
    }
}

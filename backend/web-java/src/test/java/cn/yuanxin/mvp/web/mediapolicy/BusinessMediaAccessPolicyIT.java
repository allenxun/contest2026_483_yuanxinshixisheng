package cn.yuanxin.mvp.web.mediapolicy;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.media.MediaObject;
import cn.yuanxin.mvp.web.media.MediaPurpose;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * B 统一业务 {@code @Primary MediaAccessPolicy} 真实 PG 集成测试（DD 10.2 / 4.3）。
 * 覆盖 SC-C-05 / SC-05-05 / SC-05-07 / SC-R-10。
 *
 * <p>冻结授权格式为 D 的 {@code report_payload.images[].media_id}（唯一）；
 * 只接受 {@code assessment_result} 用途且 T11 {@code photo_version} 精确等于
 * T05 {@code report_photo_version}。旧兼容形态（{@code public_media_ids}、
 * {@code photos[]}、{@code photo_versions}、驼峰 {@code mediaId}）与跨版本一律
 * 拒绝。fixture 全部直接 SQL 插入；图片字节经 A 的 {@link StoragePort} 测试
 * 替身真实落盘；断言同时覆盖 HTTP 层与数据库层。</p>
 */
class BusinessMediaAccessPolicyIT extends AbstractWebIT {

    /** 受控读取返回的字节内容（内容类型由 T11 行声明，读取侧不嗅探）。 */
    private static final byte[] PNG = "PNG-POLICY-BYTES".getBytes(StandardCharsets.UTF_8);

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    StoragePort storagePort;

    @Autowired
    BusinessMediaAccessPolicy policy;

    // ------------------------------------------------------------------
    // fixtures
    // ------------------------------------------------------------------

    private UUID insertIdem() {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO idempotency_requests (id, principal_type, principal_id, operation,"
                        + " idempotency_key, payload_hash, status)"
                        + " VALUES (?, 'app_account', 'fixture', 'test-fixture', ?, 'hash', 'succeeded')",
                id, "k-" + id);
        return id;
    }

    private UUID seedMember() {
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO members (id) VALUES (?)", id);
        return id;
    }

    private void seedGrant(UUID accountId, UUID memberId) {
        jdbc.update("INSERT INTO member_access_grants (account_id, member_id, status, source_request_id)"
                        + " VALUES (?, ?, 'active', ?)",
                accountId, memberId, insertIdem());
    }

    private record GimbalFixture(UUID id, String authRef, long credentialVersion, String token) {
    }

    private GimbalFixture seedGimbalAndLogin(UUID boundAccountId, long credentialVersion)
            throws Exception {
        UUID id = UUID.randomUUID();
        String authRef = "authref-" + id;
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version,"
                        + " bound_account_id) VALUES (?, ?, ?, ?, ?)",
                id, "SN-" + id, authRef, credentialVersion, boundAccountId);
        MvcResult r = mockMvc.perform(post("/api/v1/gimbal-sessions")
                        .contentType("application/json")
                        .content("{\"credential\":\"" + authRef + "\",\"credentialVersion\":\""
                                + credentialVersion + "\",\"proof\":\"p\"}"))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        return new GimbalFixture(id, authRef, credentialVersion,
                bodyNode(r).path("data").path("sessionToken").asText());
    }

    /** T05 建行；source_request_id 必填（FK T13）。非 report_ready 时报告字段为空。 */
    private UUID seedAssessment(UUID gimbalId, UUID memberId, String status,
                               String reportPayload, Long reportPhotoVersion,
                               String photoVersions) {
        UUID id = UUID.randomUUID();
        boolean ready = "report_ready".equals(status);
        jdbc.update("INSERT INTO skin_assessments (id, gimbal_id, member_id, status,"
                        + " current_photo_version, report_id, report_payload, report_photo_version,"
                        + " report_ready_at, photo_versions, source_request_id)"
                        + " VALUES (?, ?, ?, ?, 1, ?, ?::jsonb, ?, ?, ?::jsonb, ?)",
                id, gimbalId, memberId, status,
                ready ? UUID.randomUUID() : null,
                reportPayload,
                reportPhotoVersion,
                ready ? java.sql.Timestamp.from(java.time.Instant.now()) : null,
                photoVersions, insertIdem());
        return id;
    }

    private UUID seedMedia(UUID id, MediaPurpose purpose, String state, UUID assessmentId,
                          Long photoVersion, UUID memberId, String uploaderType,
                          String uploaderRef, byte[] bytes) {
        String objectKey = "test/" + purpose.dbValue() + "/" + id;
        storagePort.put(objectKey, new ByteArrayInputStream(bytes), bytes.length, "image/png");
        jdbc.update("INSERT INTO media_objects (id, bucket, object_key, purpose, assessment_id,"
                        + " photo_version, member_id, uploader_type, uploader_ref, state, content_type,"
                        + " byte_size, content_hash, storage_metadata)"
                        + " VALUES (?, 'mvp-a-test', ?, ?, ?, ?, ?, ?, ?, ?, 'image/png', ?, ?,"
                        + " '{\"schema_version\":1}'::jsonb)",
                id, objectKey, purpose.dbValue(), assessmentId, photoVersion, memberId,
                uploaderType, uploaderRef, state, (long) bytes.length, sha256Hex(bytes));
        return id;
    }

    // ---- 冻结格式 / 旧兼容形态 payload 构造 ----

    /** D 冻结格式：{@code {"schema_version":1,"images":[{"media_id":"..."}]}}。 */
    private static String frozenImages(UUID... ids) {
        StringBuilder sb = new StringBuilder("{\"schema_version\":1,\"images\":[");
        for (int i = 0; i < ids.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append("{\"media_id\":\"").append(ids[i]).append("\"}");
        }
        return sb.append("]}").toString();
    }

    private static String legacyPublicMediaIds(UUID id) {
        return "{\"schema_version\":1,\"public_media_ids\":[\"" + id + "\"]}";
    }

    private static String legacyPhotosPublic(UUID id) {
        return "{\"schema_version\":1,\"photos\":[{\"media_id\":\"" + id + "\",\"public\":true}]}";
    }

    private static String legacyImagesCamelCase(UUID id) {
        return "{\"schema_version\":1,\"images\":[{\"mediaId\":\"" + id + "\"}]}";
    }

    private static String legacyPhotoVersionsPublic(UUID id) {
        return "{\"schema_version\":1,\"versions\":{\"a\":{\"media_id\":\"" + id
                + "\",\"public\":true}}}";
    }

    private record AppFixture(LoginResult account, String installationId, UUID memberId,
                              GimbalFixture gimbal, UUID assessmentId, UUID mediaId) {
    }

    /** account + active T02 + report_ready frozen-images T05 + available assessment_result media. */
    private AppFixture positiveAppFixture() throws Exception {
        String installationId = "inst-" + UUID.randomUUID().toString().substring(0, 8);
        LoginResult account = loginAppWithInstallation(newPhone(), installationId);
        UUID accountId = UUID.fromString(account.accountId());
        UUID memberId = seedMember();
        seedGrant(accountId, memberId);
        GimbalFixture gimbal = seedGimbalAndLogin(accountId, 1L);
        UUID mediaId = UUID.randomUUID();
        UUID assessmentId = seedAssessment(gimbal.id(), memberId, "report_ready",
                frozenImages(mediaId), 1L, "{}");
        seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L, memberId,
                "app", accountId + ":" + installationId, PNG);
        return new AppFixture(account, installationId, memberId, gimbal, assessmentId, mediaId);
    }

    // ------------------------------------------------------------------
    // HTTP helpers
    // ------------------------------------------------------------------

    private MvcResult getMedia(String token, UUID mediaId) throws Exception {
        return mockMvc.perform(get("/api/v1/media/" + mediaId + "/content")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
    }

    private void assertVisible(String token, UUID mediaId, byte[] expected) throws Exception {
        MvcResult r = getMedia(token, mediaId);
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("image/png", r.getResponse().getContentType());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        assertEquals("nosniff", r.getResponse().getHeader("X-Content-Type-Options"));
        assertNotNull(r.getResponse().getHeader("X-Request-Id"));
        assertArrayEquals(expected, r.getResponse().getContentAsByteArray());
    }

    private void assertNotVisible(String token, UUID mediaId) throws Exception {
        MvcResult r = getMedia(token, mediaId);
        assertEquals(404, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("RESOURCE_NOT_VISIBLE", errorCode(r));
    }

    private static JsonNode bodyNode(MvcResult r) throws Exception {
        return JSON.readTree(r.getResponse().getContentAsString());
    }

    private static String errorCode(MvcResult r) throws Exception {
        return bodyNode(r).path("error").path("code").asText();
    }

    private static String sha256Hex(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    // ------------------------------------------------------------------
    // 测试组 1：APP 正例（冻结格式命中）
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G1 APP 正例：report_ready 冻结 images[].media_id 命中 + 版本一致 + active T02 → 200")
    void appPositiveRead() throws Exception {
        AppFixture f = positiveAppFixture();
        assertVisible(f.account().accessToken(), f.mediaId(), PNG);

        // DB 层：图片仍 available、T02 仍 active、T05 仍 report_ready
        assertEquals("available", jdbc.queryForObject(
                "SELECT state FROM media_objects WHERE id = ?", String.class, f.mediaId()));
        assertEquals("active", jdbc.queryForObject(
                "SELECT status FROM member_access_grants WHERE account_id = ? AND member_id = ?",
                String.class, UUID.fromString(f.account().accountId()), f.memberId()));
        assertEquals("report_ready", jdbc.queryForObject(
                "SELECT status FROM skin_assessments WHERE id = ?", String.class, f.assessmentId()));
    }

    // ------------------------------------------------------------------
    // 测试组 2：撤销即失效 + 404 不可区分
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G2 撤销 T02 即时失效：同一 mediaId 404，且与不存在 mediaId 逐字节一致（掩蔽 requestId）")
    void revocationImmediateAndIndistinguishable() throws Exception {
        AppFixture f = positiveAppFixture();
        assertVisible(f.account().accessToken(), f.mediaId(), PNG);

        jdbc.update("UPDATE member_access_grants SET status = 'revoked', revoked_at = now()"
                + " WHERE account_id = ? AND member_id = ?",
                UUID.fromString(f.account().accountId()), f.memberId());
        // 无缓存：同一 token、同一 mediaId 立即 404
        MvcResult revoked = getMedia(f.account().accessToken(), f.mediaId());
        assertEquals(404, revoked.getResponse().getStatus());
        assertEquals("RESOURCE_NOT_VISIBLE", errorCode(revoked));

        MvcResult missing = getMedia(f.account().accessToken(), UUID.randomUUID());
        assertEquals(404, missing.getResponse().getStatus());
        assertEquals("RESOURCE_NOT_VISIBLE", errorCode(missing));

        // 掩蔽契约强制的 per-attempt requestId 后逐字节一致（不存在性与归属不可区分）
        String rawRevoked = revoked.getResponse().getContentAsString();
        String rawMissing = missing.getResponse().getContentAsString();
        String idRevoked = bodyNode(revoked).path("requestId").asText();
        String idMissing = bodyNode(missing).path("requestId").asText();
        assertNotEquals(idRevoked, idMissing);
        assertEquals(rawRevoked.replace(idRevoked, "<requestId>"),
                rawMissing.replace(idMissing, "<requestId>"));
        assertEquals("media not visible", bodyNode(revoked).path("error").path("message").asText());
        assertEquals("media not visible", bodyNode(missing).path("error").path("message").asText());
    }

    // ------------------------------------------------------------------
    // 测试组 3：未授权 / 他人账号
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G3 无授权账号 / 他人账号（对别的成员 active）→ 404 不可区分")
    void unauthorizedAndOtherAccountDenied() throws Exception {
        AppFixture f = positiveAppFixture();

        // 无任何 T02 的账号 → 404
        LoginResult stranger = loginAppWithInstallation(newPhone(), "inst-stranger");
        assertNotVisible(stranger.accessToken(), f.mediaId());

        // 对另一成员有 active 关系，但对本媒体成员无 → 404
        LoginResult other = loginAppWithInstallation(newPhone(), "inst-other");
        UUID otherMember = seedMember();
        seedGrant(UUID.fromString(other.accountId()), otherMember);
        assertNotVisible(other.accessToken(), f.mediaId());

        // 不存在 mediaId 同样 404（与无授权不可区分）
        assertNotVisible(f.account().accessToken(), UUID.randomUUID());
    }

    // ------------------------------------------------------------------
    // 测试组 4：云台绑定不替代成员授权（SC-05-07）
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G4 SC-05-07：账号绑定了云台但无 active T02 → 404（绑定不替代成员授权）")
    void gimbalBindingDoesNotSubstituteGrant() throws Exception {
        String installationId = "inst-bind-" + UUID.randomUUID().toString().substring(0, 8);
        LoginResult account = loginAppWithInstallation(newPhone(), installationId);
        UUID accountId = UUID.fromString(account.accountId());
        UUID memberId = seedMember(); // 故意不建 T02
        GimbalFixture gimbal = seedGimbalAndLogin(accountId, 1L);
        UUID mediaId = UUID.randomUUID();
        UUID assessmentId = seedAssessment(gimbal.id(), memberId, "report_ready",
                frozenImages(mediaId), 1L, "{}");
        seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L, memberId,
                "app", accountId + ":" + installationId, PNG);
        jdbc.update("UPDATE gimbals SET current_assessment_id = ? WHERE id = ?",
                assessmentId, gimbal.id());

        assertNotVisible(account.accessToken(), mediaId);
    }

    // ------------------------------------------------------------------
    // 测试组 5/6：云台正例 / 旧任务 / 凭据轮换
    // ------------------------------------------------------------------

    private record GimbalScenario(GimbalFixture gimbal, UUID memberId, UUID assessmentId,
                                  UUID mediaId) {
    }

    private GimbalScenario gimbalScenario(GimbalFixture gimbal, UUID memberId) {
        UUID mediaId = UUID.randomUUID();
        UUID assessmentId = seedAssessment(gimbal.id(), memberId, "report_ready",
                frozenImages(mediaId), 1L, "{}");
        seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L, memberId,
                "gimbal", gimbal.id().toString(), PNG);
        jdbc.update("UPDATE gimbals SET current_assessment_id = ? WHERE id = ?",
                assessmentId, gimbal.id());
        return new GimbalScenario(gimbal, memberId, assessmentId, mediaId);
    }

    @Test
    @DisplayName("G5 云台正例：current_assessment_id==任务 且 credential_version 匹配 → 200")
    void gimbalPositiveCurrentTask() throws Exception {
        UUID memberId = seedMember();
        GimbalFixture gimbal = seedGimbalAndLogin(null, 1L);
        GimbalScenario s = gimbalScenario(gimbal, memberId);

        assertVisible(gimbal.token(), s.mediaId(), PNG);
    }

    @Test
    @DisplayName("G6 SC-R-10：current_assessment_id 移走后旧任务 404；credential_version 递增后旧 token 401")
    void gimbalOnlyCurrentTaskAndCredentialRotation() throws Exception {
        UUID memberId = seedMember();
        GimbalFixture gimbal = seedGimbalAndLogin(null, 1L);
        GimbalScenario old = gimbalScenario(gimbal, memberId);
        assertVisible(gimbal.token(), old.mediaId(), PNG);

        // 同一云台的第二个任务成为 current → 旧任务图片立即 404
        GimbalScenario newer = gimbalScenario(gimbal, memberId);
        assertNotVisible(gimbal.token(), old.mediaId());
        assertVisible(gimbal.token(), newer.mediaId(), PNG);

        // 凭据代次递增：旧 token 由 A 的 revalidator 统一 401（SESSION_INVALID）
        jdbc.update("UPDATE gimbals SET credential_version = credential_version + 1 WHERE id = ?",
                gimbal.id());
        MvcResult rotated = getMedia(gimbal.token(), newer.mediaId());
        assertEquals(401, rotated.getResponse().getStatus(), rotated.getResponse().getContentAsString());
        assertEquals("SESSION_INVALID", errorCode(rotated));
    }

    @Test
    @DisplayName("G6b 策略层 credential_version 不符 → 直接判定 false（绕过会话层也拒绝）")
    void gimbalPolicyCredentialVersionMismatchDenied() {
        UUID memberId = seedMember();
        UUID gimbalId = UUID.randomUUID();
        jdbc.update("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
                + " VALUES (?, ?, ?, 1)", gimbalId, "SN-" + gimbalId, "authref-" + gimbalId);
        UUID mediaId = UUID.randomUUID();
        UUID assessmentId = seedAssessment(gimbalId, memberId, "report_ready",
                frozenImages(mediaId), 1L, "{}");
        seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L, memberId,
                "gimbal", gimbalId.toString(), PNG);
        jdbc.update("UPDATE gimbals SET current_assessment_id = ? WHERE id = ?",
                assessmentId, gimbalId);

        assertTrue(policy.canAccess(gimbalPrincipal(gimbalId, 1L), resultMedia(mediaId)),
                "匹配代次应放行");
        assertFalse(policy.canAccess(gimbalPrincipal(gimbalId, 2L), resultMedia(mediaId)),
                "credential_version 不符必须拒绝");
    }

    private static PrincipalContext gimbalPrincipal(UUID gimbalId, long credentialVersion) {
        return new PrincipalContext(PrincipalType.GIMBAL, null, null, gimbalId,
                credentialVersion, "session", "req");
    }

    private static MediaObject resultMedia(UUID mediaId) {
        return new MediaObject(mediaId, "mvp-a-test", "test/key", MediaPurpose.ASSESSMENT_RESULT,
                "available", "gimbal", "ref", null, "image/png", 1L, "hash");
    }

    // ------------------------------------------------------------------
    // 测试组 7：非 assessment_result 用途一律拒绝
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G7 assessment_source + face 三用途 × 上传者/已授权 APP/当前任务云台 → 全部 404（用途最优先）")
    void nonResultPurposesNeverVisible() throws Exception {
        String installationId = "inst-face-" + UUID.randomUUID().toString().substring(0, 8);
        LoginResult account = loginAppWithInstallation(newPhone(), installationId);
        UUID accountId = UUID.fromString(account.accountId());
        UUID memberId = seedMember();
        seedGrant(accountId, memberId);
        GimbalFixture gimbal = seedGimbalAndLogin(accountId, 1L);

        for (MediaPurpose purpose : List.of(MediaPurpose.ASSESSMENT_SOURCE,
                MediaPurpose.GRANT_FACE, MediaPurpose.EXECUTION_FACE,
                MediaPurpose.REVALIDATION_FACE)) {
            UUID mediaId = UUID.randomUUID();
            // 归属、冻结报告引用、active T02、当前任务全部齐备——仍必须拒绝
            UUID assessmentId = seedAssessment(gimbal.id(), memberId, "report_ready",
                    frozenImages(mediaId), 1L, "{}");
            seedMedia(mediaId, purpose, "available", assessmentId, 1L, memberId,
                    "app", accountId + ":" + installationId, PNG);
            jdbc.update("UPDATE gimbals SET current_assessment_id = ? WHERE id = ?",
                    assessmentId, gimbal.id());

            // 上传者/已授权 APP
            assertNotVisible(account.accessToken(), mediaId);
            // 当前任务云台
            assertNotVisible(gimbal.token(), mediaId);
        }
    }

    // ------------------------------------------------------------------
    // 测试组 8：未接纳 / 未发布 / deny-by-default 判别力
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G8 非 available、无任务归属、非 report_ready、images 空、未引用全 404；补引用后 200")
    void notAcceptedOrNotPublishedDenied() throws Exception {
        AppFixture base = positiveAppFixture();
        String token = base.account().accessToken();
        UUID accountId = UUID.fromString(base.account().accountId());
        UUID memberId = base.memberId();
        UUID gimbalId = base.gimbal().id();
        String uploader = accountId + ":" + base.installationId();

        // (a) state != available（pending/failed/deleting/deleted）
        for (String state : List.of("pending", "failed", "deleting", "deleted")) {
            UUID mediaId = UUID.randomUUID();
            seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, state, base.assessmentId(), 1L,
                    memberId, "app", uploader, PNG);
            assertNotVisible(token, mediaId);
        }

        // (b) available 但 assessment_id IS NULL（未被业务接纳）
        UUID orphan = UUID.randomUUID();
        seedMedia(orphan, MediaPurpose.ASSESSMENT_RESULT, "available", null, null, memberId,
                "app", uploader, PNG);
        assertNotVisible(token, orphan);

        // (c) T05 非 report_ready 状态
        for (String status : List.of("queued", "analyzing", "needs_retake", "failed")) {
            UUID mediaId = UUID.randomUUID();
            UUID assessmentId = seedAssessment(gimbalId, memberId, status, null, null, "{}");
            seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L,
                    memberId, "app", uploader, PNG);
            assertNotVisible(token, mediaId);
        }

        // (d) report_payload 缺 images 键 / images 为空数组 → 404
        for (String payload : List.of("{\"schema_version\":1}",
                "{\"schema_version\":1,\"images\":[]}")) {
            UUID mediaId = UUID.randomUUID();
            UUID assessmentId = seedAssessment(gimbalId, memberId, "report_ready",
                    payload, 1L, "{}");
            seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L,
                    memberId, "app", uploader, PNG);
            assertNotVisible(token, mediaId);
        }

        // (e) deny-by-default 判别力：images 引用别的 id → 404；改引用本 id → 200
        UUID discriminated = UUID.randomUUID();
        UUID assessmentDisc = seedAssessment(gimbalId, memberId, "report_ready",
                frozenImages(UUID.randomUUID()), 1L, "{}");
        seedMedia(discriminated, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentDisc, 1L,
                memberId, "app", uploader, PNG);
        assertNotVisible(token, discriminated);

        jdbc.update("UPDATE skin_assessments SET report_payload = ?::jsonb, updated_at = now()"
                + " WHERE id = ?", frozenImages(discriminated), assessmentDisc);
        assertVisible(token, discriminated, PNG);
    }

    // ------------------------------------------------------------------
    // 测试组 9：旧兼容形态与跨版本串图
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G9 旧兼容形态全部拒绝：public_media_ids / photos[].public / 驼峰 mediaId / photo_versions")
    void legacyCompatibilityShapesDenied() throws Exception {
        AppFixture base = positiveAppFixture();
        String token = base.account().accessToken();
        UUID accountId = UUID.fromString(base.account().accountId());
        UUID memberId = base.memberId();
        UUID gimbalId = base.gimbal().id();
        String uploader = accountId + ":" + base.installationId();

        // 每个 media 的 T11.photo_version 与 T05.report_photo_version 都一致（=1），
        // 唯一被拒原因就是旧兼容形状本身。
        for (var shape : List.of(
                (java.util.function.Function<UUID, String>) BusinessMediaAccessPolicyIT::legacyPublicMediaIds,
                (java.util.function.Function<UUID, String>) BusinessMediaAccessPolicyIT::legacyPhotosPublic,
                (java.util.function.Function<UUID, String>) BusinessMediaAccessPolicyIT::legacyImagesCamelCase)) {
            UUID mediaId = UUID.randomUUID();
            UUID assessmentId = seedAssessment(gimbalId, memberId, "report_ready",
                    shape.apply(mediaId), 1L, "{}");
            seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L,
                    memberId, "app", uploader, PNG);
            assertNotVisible(token, mediaId);
        }

        // T05 photo_versions 中的 public 项不再被采信（report_payload 本身不含引用）。
        UUID viaPhotoVersions = UUID.randomUUID();
        UUID assessmentId = seedAssessment(gimbalId, memberId, "report_ready",
                frozenImages(), 1L, legacyPhotoVersionsPublic(viaPhotoVersions));
        seedMedia(viaPhotoVersions, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L,
                memberId, "app", uploader, PNG);
        assertNotVisible(token, viaPhotoVersions);
    }

    @Test
    @DisplayName("G9b 跨照片版本一律拒绝：photo_version != report_photo_version（即使被 images 引用）→ 404")
    void crossPhotoVersionAlwaysDenied() throws Exception {
        AppFixture base = positiveAppFixture();
        String token = base.account().accessToken();
        UUID accountId = UUID.fromString(base.account().accountId());
        UUID memberId = base.memberId();
        UUID gimbalId = base.gimbal().id();
        String uploader = accountId + ":" + base.installationId();

        // 报告 report_photo_version=1，媒体 photo_version=2（即便被 images 引用）→ 404
        UUID mismatched = UUID.randomUUID();
        UUID a1 = seedAssessment(gimbalId, memberId, "report_ready",
                frozenImages(mismatched), 1L, "{}");
        seedMedia(mismatched, MediaPurpose.ASSESSMENT_RESULT, "available", a1, 2L,
                memberId, "app", uploader, PNG);
        assertNotVisible(token, mismatched);

        // 媒体 photo_version 为 NULL → 拒绝
        UUID nullVersion = UUID.randomUUID();
        UUID a2 = seedAssessment(gimbalId, memberId, "report_ready",
                frozenImages(nullVersion), 1L, "{}");
        seedMedia(nullVersion, MediaPurpose.ASSESSMENT_RESULT, "available", a2, null,
                memberId, "app", uploader, PNG);
        assertNotVisible(token, nullVersion);

        // 版本一致且被引用 → 200
        UUID matched = UUID.randomUUID();
        UUID a3 = seedAssessment(gimbalId, memberId, "report_ready",
                frozenImages(matched), 2L, "{}");
        seedMedia(matched, MediaPurpose.ASSESSMENT_RESULT, "available", a3, 2L,
                memberId, "app", uploader, PNG);
        assertVisible(token, matched, PNG);
    }

    @Test
    @DisplayName("G9c assessment 归属必须精确：媒体 assessment_id 指向的报告不引用该图 → 404（即使别报告引用）")
    void assessmentLinkageRequiredNotAnyReport() throws Exception {
        AppFixture base = positiveAppFixture();
        String token = base.account().accessToken();
        UUID accountId = UUID.fromString(base.account().accountId());
        UUID memberId = base.memberId();
        UUID gimbalId = base.gimbal().id();
        String uploader = accountId + ":" + base.installationId();

        UUID target = UUID.randomUUID();
        // 媒体归属 T05 A，A 的 images 引用的是另一张图 → 拒绝
        UUID a = seedAssessment(gimbalId, memberId, "report_ready",
                frozenImages(UUID.randomUUID()), 1L, "{}");
        seedMedia(target, MediaPurpose.ASSESSMENT_RESULT, "available", a, 1L,
                memberId, "app", uploader, PNG);
        // 另一个 report_ready T05 B 确实引用 target，但媒体不属于 B → 仍拒绝
        seedAssessment(gimbalId, memberId, "report_ready", frozenImages(target), 1L, "{}");
        assertNotVisible(token, target);
    }

    // ------------------------------------------------------------------
    // 测试组 10：解析容错（形状漂移一律拒绝，绝不 500）
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G10 report_payload 形状漂移（类型不符/嵌套/非 UUID）→ 404 RESOURCE_NOT_VISIBLE，绝不 500")
    void malformedPayloadsDeniedTolerantly() throws Exception {
        AppFixture base = positiveAppFixture();
        String token = base.account().accessToken();
        UUID accountId = UUID.fromString(base.account().accountId());
        UUID memberId = base.memberId();
        String uploader = accountId + ":" + base.installationId();

        // 全部是合法 JSON 对象且 schema_version 为 number（T05 CHECK 允许），
        // 但 images 形状不符，策略必须容错拒绝而非 500。
        List<String> shapes = List.of(
                "{\"schema_version\":1,\"images\":\"not-an-array\"}",
                "{\"schema_version\":1,\"images\":[123,true,null,{}]}",
                "{\"schema_version\":1,\"images\":null}",
                "{\"schema_version\":1,\"images\":[[[\"nested\"]]]}",
                "{\"schema_version\":1,\"images\":{\"media_id\":\"x\"}}",
                "{\"schema_version\":1,\"images\":[{\"media_id\":\"not-a-uuid\"}]}");
        for (String payload : shapes) {
            UUID mediaId = UUID.randomUUID();
            UUID assessmentId = seedAssessment(base.gimbal().id(), memberId, "report_ready",
                    payload, 1L, "{}");
            seedMedia(mediaId, MediaPurpose.ASSESSMENT_RESULT, "available", assessmentId, 1L,
                    memberId, "app", uploader, PNG);
            MvcResult r = getMedia(token, mediaId);
            assertEquals(404, r.getResponse().getStatus(),
                    "payload must be denied, got " + r.getResponse().getStatus() + ": " + payload);
            assertEquals("RESOURCE_NOT_VISIBLE", errorCode(r));
        }
    }

    // ------------------------------------------------------------------
    // 测试组 11：只读无副作用
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G11 全部 GET 后 T11/T05/T02/T03 相关行零变化（策略只读，无任务/revision 副作用）")
    void readOnlyNoSideEffects() throws Exception {
        AppFixture f = positiveAppFixture();
        String accountSnapshot = snapshot("member_access_grants", grantIdOf(
                UUID.fromString(f.account().accountId()), f.memberId()));
        String mediaSnapshot = snapshot("media_objects", f.mediaId());
        String assessmentSnapshot = snapshot("skin_assessments", f.assessmentId());
        String gimbalSnapshot = snapshot("gimbals", f.gimbal().id());
        Integer jobsBefore = jdbc.queryForObject("SELECT count(*) FROM async_jobs", Integer.class);

        assertVisible(f.account().accessToken(), f.mediaId(), PNG);
        assertNotVisible(f.account().accessToken(), UUID.randomUUID());
        assertNotVisible(f.gimbal().token(), f.mediaId()); // 云台当前任务指针未指向该任务

        assertEquals(accountSnapshot, snapshot("member_access_grants", grantIdOf(
                UUID.fromString(f.account().accountId()), f.memberId())));
        assertEquals(mediaSnapshot, snapshot("media_objects", f.mediaId()));
        assertEquals(assessmentSnapshot, snapshot("skin_assessments", f.assessmentId()));
        assertEquals(gimbalSnapshot, snapshot("gimbals", f.gimbal().id()));
        assertEquals(jobsBefore, jdbc.queryForObject("SELECT count(*) FROM async_jobs", Integer.class));
    }

    // ------------------------------------------------------------------
    // 测试组 12：T11.member_id 非权威，跨成员越权 fail closed
    // ------------------------------------------------------------------

    @Test
    @DisplayName("G12 T11.member_id 非权威：T05 属 A 而 T11 写成 B → 不一致 fail closed（A、B 均 404）；一致/NULL 时按 T05 判定")
    void t11MemberIsNotAuthoritative() throws Exception {
        String instA = "inst-auth-" + UUID.randomUUID().toString().substring(0, 8);
        LoginResult accountA = loginAppWithInstallation(newPhone(), instA);
        UUID accountAId = UUID.fromString(accountA.accountId());
        String instB = "inst-auth-" + UUID.randomUUID().toString().substring(0, 8);
        LoginResult accountB = loginAppWithInstallation(newPhone(), instB);
        UUID accountBId = UUID.fromString(accountB.accountId());

        UUID memberA = seedMember();
        UUID memberB = seedMember();
        seedGrant(accountAId, memberA);
        seedGrant(accountBId, memberB);

        GimbalFixture gimbal = seedGimbalAndLogin(accountAId, 1L);
        String uploaderA = accountAId + ":" + instA;
        String uploaderB = accountBId + ":" + instB;

        // (a) T05 属 memberA，T11.member_id 误写成 memberB（跨表不一致）
        //     → 归属不可信，fail closed：仅持 B 授权、甚至持 A 授权都 404。
        UUID inconsistent = UUID.randomUUID();
        UUID inconsistentAssessment = seedAssessment(gimbal.id(), memberA, "report_ready",
                frozenImages(inconsistent), 1L, "{}");
        seedMedia(inconsistent, MediaPurpose.ASSESSMENT_RESULT, "available", inconsistentAssessment,
                1L, memberB, "app", uploaderB, PNG);
        assertNotVisible(accountB.accessToken(), inconsistent);
        assertNotVisible(accountA.accessToken(), inconsistent);

        // (b) T11.member_id 与 T05.member_id 一致（=memberA）→ 仅 T05 成员 A 可读，B 仍 404。
        UUID consistent = UUID.randomUUID();
        UUID consistentAssessment = seedAssessment(gimbal.id(), memberA, "report_ready",
                frozenImages(consistent), 1L, "{}");
        seedMedia(consistent, MediaPurpose.ASSESSMENT_RESULT, "available", consistentAssessment,
                1L, memberA, "app", uploaderA, PNG);
        assertVisible(accountA.accessToken(), consistent, PNG);
        assertNotVisible(accountB.accessToken(), consistent);

        // (c) T11.member_id 为 NULL → 仍只按 T05 判定放行。
        UUID nullMemberMedia = UUID.randomUUID();
        UUID nullMemberAssessment = seedAssessment(gimbal.id(), memberA, "report_ready",
                frozenImages(nullMemberMedia), 1L, "{}");
        seedMedia(nullMemberMedia, MediaPurpose.ASSESSMENT_RESULT, "available",
                nullMemberAssessment, 1L, null, "app", uploaderA, PNG);
        assertVisible(accountA.accessToken(), nullMemberMedia, PNG);
    }

    private UUID grantIdOf(UUID accountId, UUID memberId) {
        return jdbc.queryForObject("SELECT id FROM member_access_grants"
                + " WHERE account_id = ? AND member_id = ?", UUID.class, accountId, memberId);
    }

    /** 整行快照（表名与 id 均来自测试常量，非用户输入）。 */
    private String snapshot(String table, UUID id) {
        return jdbc.queryForObject("SELECT to_jsonb(t)::text FROM " + table + " t WHERE t.id = ?",
                String.class, id);
    }
}

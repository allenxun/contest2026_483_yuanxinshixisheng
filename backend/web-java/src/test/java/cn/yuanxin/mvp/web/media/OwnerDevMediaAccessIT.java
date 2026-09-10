package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/**
 * dev/test 上传者便利（{@code app.media.access-mode=owner-dev}）：
 * 仅非人脸用途、且仅上传者本人可读；他人/同账号换安装/匿名/核验用途均拒绝。
 * 与默认 deny-all 的 {@link MediaFoundationIT} 使用不同测试上下文（属性不同）。
 */
@TestPropertySource(properties = "app.media.access-mode=owner-dev")
class OwnerDevMediaAccessIT extends AbstractWebIT {

    @Autowired
    MediaIntakeService intakeService;

    private static final byte[] PNG = new byte[]{(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A,
            0, 0, 0, 9, 'I', 'H', 'D', 'R'};

    @Test
    @DisplayName("owner-dev：非人脸用途上传者 200（no-store/nosniff）；他人/同账号换安装 404；匿名 401")
    void ownerDevNonFacePossitive() throws Exception {
        String ownerPhone = newPhone();
        LoginResult owner = loginAppWithInstallation(ownerPhone, "inst-od-1");
        var ownerPrincipal = cn.yuanxin.mvp.web.auth.PrincipalContext.forApp(
                cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal.app(
                        UUID.fromString(owner.accountId()), "inst-od-1", "s-od", 1L),
                "req-od");
        MediaIntakeService.IngestedMedia ing = intakeService.ingest(
                ownerPrincipal, MediaPurpose.ASSESSMENT_SOURCE, null, Map.of("front", PNG))
                .values().iterator().next();

        MvcResult r = mockMvc.perform(get("/api/v1/media/" + ing.media().id() + "/content")
                        .header("Authorization", "Bearer " + owner.accessToken()))
                .andReturn();
        assertEquals(200, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        assertEquals("no-store", r.getResponse().getHeader("Cache-Control"));
        assertEquals("nosniff", r.getResponse().getHeader("X-Content-Type-Options"));
        assertEquals("image/png", r.getResponse().getContentType());
        assertEquals(PNG.length, r.getResponse().getContentAsByteArray().length);
        assertTrue(r.getResponse().getHeader("X-Request-Id") != null
                && !r.getResponse().getHeader("X-Request-Id").isBlank());

        // 他人 → 404
        LoginResult other = loginAppWithInstallation(newPhone(), "inst-od-other");
        assertNotVisible(other.accessToken(), ing.media().id());

        // 同账号、不同 installation → 404
        LoginResult sameAcctOtherInst = loginAppWithInstallation(ownerPhone, "inst-od-2");
        assertNotVisible(sameAcctOtherInst.accessToken(), ing.media().id());

        // 匿名 → 401
        MvcResult anon = mockMvc.perform(get("/api/v1/media/" + ing.media().id() + "/content"))
                .andReturn();
        assertEquals(401, anon.getResponse().getStatus());
    }

    @Test
    @DisplayName("owner-dev：核验用途（GRANT_FACE）即使上传者也 404——便利策略不服务人脸")
    void ownerDevDeniesFacePurposes() throws Exception {
        LoginResult owner = loginAppWithInstallation(newPhone(), "inst-od-face");
        var ownerPrincipal = cn.yuanxin.mvp.web.auth.PrincipalContext.forApp(
                cn.yuanxin.mvp.web.auth.AuthenticatedPrincipal.app(
                        UUID.fromString(owner.accountId()), "inst-od-face", "s-od-f", 1L),
                "req-od-f");
        MediaIntakeService.IngestedMedia face = intakeService.ingest(
                ownerPrincipal, MediaPurpose.GRANT_FACE, null, Map.of("face", PNG))
                .values().iterator().next();
        assertEquals("available", face.media().state());
        assertNotVisible(owner.accessToken(), face.media().id());
    }

    private void assertNotVisible(String token, UUID mediaId) throws Exception {
        MvcResult r = mockMvc.perform(get("/api/v1/media/" + mediaId + "/content")
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertEquals(404, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode err = JSON.readTree(r.getResponse().getContentAsString());
        assertEquals("RESOURCE_NOT_VISIBLE", err.path("error").path("code").asText());
    }
}

package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.face.FaceServiceError;
import cn.yuanxin.mvp.web.face.FaceServiceException;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

/**
 * M1-A01 第二次搜索（{@code FaceIdentityResolver.resolve} 内部的 1:N 搜索）依赖故障的映射测试。
 *
 * <p>缺陷背景：`FaceServiceException extends RuntimeException`，而 {@code MemberAccessGrantService}
 * 原先未捕获 {@code resolve} 的异常 ⇒ insightface 模式下第二次搜索遇到依赖故障时会被兜底
 * {@code @ExceptionHandler(Exception.class)} 渲染成 <b>500 INTERNAL、retryable=false</b>，
 * 而同一方法对第一次搜索（{@code classify → DEPENDENCY_FAILED}）明确给出 503
 * {@code DEPENDENCY_UNAVAILABLE}（可重试）。本测试用真实 HTTP 入口锁定修复后的 503 行为。
 *
 * <p>用 {@link MockitoBean} 替换 {@code FaceIdentityResolver}，令其 {@code resolve} 抛真实的
 * {@link FaceServiceException}（模拟端口在第二次搜索时抛出的依赖故障）；默认 doubles
 * {@code FaceProvider} 返回 {@code MATCHED}，因此流程必然执行到
 * {@code MemberAccessGrantService} 的 resolve 调用点与新增的 catch 映射。
 */
class MemberAccessGrantFaceDependencyFailureIT extends AbstractWebIT {

    private static final byte[] PNG_HEADER = {
            (byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};

    @MockitoBean
    FaceIdentityResolver faceIdentityResolver;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    @DisplayName("第二次搜索依赖故障 ⇒ 503 DEPENDENCY_UNAVAILABLE(retryable)，不是 500、不是 403；无 grant 行、T13 留 processing")
    void identityResolutionDependencyFailureIsRetryable503() throws Exception {
        when(faceIdentityResolver.resolve(any(), any())).thenThrow(new FaceServiceException(
                new FaceServiceError("MODEL_UNAVAILABLE", "stub dependency down", true, "r-dep", 503)));

        LoginResult account = loginAppWithInstallation(newPhone(),
                "inst-" + UUID.randomUUID().toString().substring(0, 8));
        UUID accountId = UUID.fromString(account.accountId());

        byte[] face = new byte[PNG_HEADER.length + 4];
        System.arraycopy(PNG_HEADER, 0, face, 0, PNG_HEADER.length);
        String key = "k-" + UUID.randomUUID();
        MockMultipartFile metadata = new MockMultipartFile("metadata", "metadata", "application/json",
                ("{\"capture\":{\"captureId\":\"cap-dep\",\"capturedAt\":\"2026-09-16T10:00:00Z\","
                        + "\"clientContinuityId\":\"cont-dep\",\"purpose\":\"grant\"},"
                        + "\"consentEvidenceRef\":\"consent-dep\"}").getBytes(StandardCharsets.UTF_8));

        MvcResult r = mockMvc.perform(multipart("/api/v1/member-access-grants")
                        .file(metadata)
                        .file(new MockMultipartFile("face", "face.png", "image/png", face))
                        .header("Authorization", "Bearer " + account.accessToken())
                        .header("Idempotency-Key", key))
                .andReturn();

        String body = r.getResponse().getContentAsString();
        assertEquals(503, r.getResponse().getStatus(), body);
        JsonNode error = JSON.readTree(body).path("error");
        assertEquals("DEPENDENCY_UNAVAILABLE", error.path("code").asText(), body);
        assertTrue(error.path("retryable").asBoolean(),
                "503 dependency failure must be retryable (not the 500 INTERNAL fallback)");

        Integer grants = jdbc.queryForObject("SELECT count(*) FROM member_access_grants"
                + " WHERE account_id = ?", Integer.class, accountId);
        assertEquals(0, grants, "no grant may be created on identity-resolution dependency failure");

        String t13Status = jdbc.queryForObject("SELECT status FROM idempotency_requests"
                + " WHERE operation = ? AND idempotency_key = ?", String.class,
                MemberAccessGrantService.OP_CREATE, key);
        assertEquals("processing", t13Status,
                "T13 must remain processing so the client can retry (same as classify dependency failure)");
    }
}
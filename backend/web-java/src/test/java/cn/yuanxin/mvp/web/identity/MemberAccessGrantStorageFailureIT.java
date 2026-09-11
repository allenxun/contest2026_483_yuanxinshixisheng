package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MvcResult;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

/**
 * lane-m1.md 必测用例 6：对象存储失败 → 503 DEPENDENCY_UNAVAILABLE，且不得
 * 当作人脸核验成功（无 T02 行、T13 未 succeeded）。
 *
 * <p>用 Mockito 替身注入可控的 StoragePort.put 失败；独立 Spring 上下文，
 * 不影响其它 IT 的真实 FileSystemStorageDouble。</p>
 */
class MemberAccessGrantStorageFailureIT extends AbstractWebIT {

    private static final byte[] PNG_HEADER = {
            (byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};

    @MockitoBean
    StoragePort storagePort;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    @DisplayName("case6: 存储写入失败 → 503，无 T02 行，T13 未 succeeded")
    void storageFailureNeverCountsAsVerification() throws Exception {
        doThrow(new UncheckedIOException("storage down", new IOException("storage down")))
                .when(storagePort).put(anyString(), any(InputStream.class), anyLong(), anyString());

        LoginResult account = loginAppWithInstallation(newPhone(),
                "inst-" + UUID.randomUUID().toString().substring(0, 8));
        UUID accountId = UUID.fromString(account.accountId());
        byte[] face = new byte[PNG_HEADER.length + 4];
        System.arraycopy(PNG_HEADER, 0, face, 0, PNG_HEADER.length);
        String key = "k-" + UUID.randomUUID();
        MockMultipartFile metadata = new MockMultipartFile("metadata", "metadata", "application/json",
                ("{\"capture\":{\"captureId\":\"cap-store\",\"capturedAt\":\"2026-09-11T10:00:00Z\","
                        + "\"clientContinuityId\":\"cont-store\",\"purpose\":\"grant\"},"
                        + "\"consentEvidenceRef\":\"consent-store\"}").getBytes(StandardCharsets.UTF_8));

        MvcResult r = mockMvc.perform(multipart("/api/v1/member-access-grants")
                        .file(metadata)
                        .file(new MockMultipartFile("face", "face.png", "image/png", face))
                        .header("Authorization", "Bearer " + account.accessToken())
                        .header("Idempotency-Key", key))
                .andReturn();

        assertEquals(503, r.getResponse().getStatus(), r.getResponse().getContentAsString());
        JsonNode error = JSON.readTree(r.getResponse().getContentAsString()).path("error");
        assertEquals("DEPENDENCY_UNAVAILABLE", error.path("code").asText());

        Integer grants = jdbc.queryForObject("SELECT count(*) FROM member_access_grants"
                + " WHERE account_id = ?", Integer.class, accountId);
        assertEquals(0, grants, "no grant may be created on storage failure");

        String t13Status = jdbc.queryForObject("SELECT status FROM idempotency_requests"
                + " WHERE operation = ? AND idempotency_key = ?", String.class,
                MemberAccessGrantService.OP_CREATE, key);
        assertEquals("processing", t13Status, "T13 must not be marked succeeded");
    }
}

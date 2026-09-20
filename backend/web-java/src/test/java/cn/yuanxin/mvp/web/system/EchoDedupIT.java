package cn.yuanxin.mvp.web.system;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/** 无 Idempotency-Key 时 dedup_key 天然幂等（JobEnqueuer replayed 路径，decisions #14）。 */
class EchoDedupIT extends AbstractWebIT {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    @DisplayName("同 jobId 无键二次提交 → 同一 jobId、单行、不报错")
    void dedupKeyNaturalReplay() throws Exception {
        String token = loginApp(newPhone());
        String jobId = UUID.randomUUID().toString();
        String body = "{\"message\":\"dedup\",\"numbersAsStrings\":[\"1\"],\"jobId\":\"" + jobId + "\"}";
        MvcResult a = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json").content(body))
                .andReturn();
        MvcResult b = mockMvc.perform(post("/api/v1/system/echo-jobs")
                        .header("Authorization", "Bearer " + token)
                        .contentType("application/json").content(body))
                .andReturn();
        assertEquals(200, a.getResponse().getStatus());
        assertEquals(200, b.getResponse().getStatus());
        JsonNode da = JSON.readTree(a.getResponse().getContentAsString()).path("data");
        JsonNode db = JSON.readTree(b.getResponse().getContentAsString()).path("data");
        assertEquals(da.path("jobId").asText(), db.path("jobId").asText());
        Integer rows = jdbc.queryForObject("SELECT count(*) FROM async_jobs WHERE dedup_key = ?",
                Integer.class, "system:echo:" + jobId);
        assertEquals(1, rows);
    }
}

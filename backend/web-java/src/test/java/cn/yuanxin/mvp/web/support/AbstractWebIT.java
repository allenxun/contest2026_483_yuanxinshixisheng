package cn.yuanxin.mvp.web.support;

import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * Web 集成测试基类：profile test + 会话级共享临时 PG + MockMvc。
 * 全部子类共用同一 Spring 上下文（同一配置），避免多容器/多库拖长总时长。
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
public abstract class AbstractWebIT {

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", TestDatabase::url);
        registry.add("spring.datasource.username", TestDatabase::user);
        registry.add("spring.datasource.password", TestDatabase::password);
    }

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected cn.yuanxin.mvp.web.auth.SessionProvider sessionProvider;

    protected static final ObjectMapper JSON = new ObjectMapper();

    /** 完整手机号登录（dev 替身固定验证码 123456），返回 accessToken。 */
    protected String loginApp(String phone) throws Exception {
        return loginAppWithInstallation(phone, "inst-" + phone.substring(phone.length() - 7)).accessToken();
    }

    protected record LoginResult(String accessToken, String refreshToken, String accountId) {
    }

    protected LoginResult loginAppWithInstallation(String phone, String installationId) throws Exception {
        MvcResult ch = mockMvc.perform(post("/api/v1/auth/sms-challenges")
                .contentType("application/json")
                .content("{\"phone\":\"" + phone + "\",\"purpose\":\"login\"}"))
                .andReturn();
        assertEquals(200, ch.getResponse().getStatus(), ch.getResponse().getContentAsString());
        String challengeId = JSON.readTree(ch.getResponse().getContentAsString())
                .path("data").path("challengeId").asText();
        MvcResult se = mockMvc.perform(post("/api/v1/auth/sessions")
                .contentType("application/json")
                .content("{\"challengeId\":\"" + challengeId
                        + "\",\"code\":\"123456\",\"installationId\":\"" + installationId + "\"}"))
                .andReturn();
        assertEquals(200, se.getResponse().getStatus(), se.getResponse().getContentAsString());
        JsonNode data = JSON.readTree(se.getResponse().getContentAsString()).path("data");
        assertNotNull(data.path("accessToken").asText(null));
        return new LoginResult(data.path("accessToken").asText(),
                data.path("refreshToken").asText(), data.path("accountId").asText());
    }

    protected String newPhone() {
        return "+86139" + String.format("%08d", Math.abs(UUID.randomUUID().getMostSignificantBits() % 100_000_000));
    }

    /** dev 替身的当前 sessionId（= T09 session_ref）。 */
    protected String sessionIdOf(String accessToken) {
        return ((InMemorySessionDouble) sessionProvider).sessionIdForAccessToken(accessToken);
    }
}

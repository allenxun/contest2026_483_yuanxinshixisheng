package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.auth.DeviceCredentialProvider;
import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.auth.SmsCodeProvider;
import cn.yuanxin.mvp.web.care.CareFaceVerifier;
import cn.yuanxin.mvp.web.care.FailClosedCareFaceVerifier;
import cn.yuanxin.mvp.web.care.MemberBindingFaceDouble;
import cn.yuanxin.mvp.web.devices.proof.ConnectionProofVerifier;
import cn.yuanxin.mvp.web.devices.proof.DevTestDoubleConnectionProofVerifier;
import cn.yuanxin.mvp.web.devices.proof.DevTestDoublePairingProofVerifier;
import cn.yuanxin.mvp.web.devices.proof.PairingProofVerifier;
import cn.yuanxin.mvp.web.identity.DevTestFaceIdentityResolver;
import cn.yuanxin.mvp.web.identity.FaceIdentityResolver;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.support.TestDatabase;
import cn.yuanxin.mvp.web.testdouble.DeviceCredentialDouble;
import cn.yuanxin.mvp.web.testdouble.FaceProviderDouble;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import cn.yuanxin.mvp.web.testdouble.SmsCodeDouble;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 环境 profile 与实现选择解耦的端到端证据：<b>仅启用 {@code local} profile</b>
 * （不叠加 {@code dev}/{@code test}）时，登录/身份/设备依赖必须完整装配为替身实现。
 *
 * <p>本类独立声明（不继承 {@code AbstractWebIT}：其固定 {@code @ActiveProfiles("test")}），
 * 用 {@link ActiveProfiles}{@code ("local")} 覆盖；断言 Spring 实际生效 profiles 恰为
 * {@code local}（{@code spring.profiles.default=dev} 不生效）。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("local")
class LocalProfileProvidersIT {

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", TestDatabase::url);
        registry.add("spring.datasource.username", TestDatabase::user);
        registry.add("spring.datasource.password", TestDatabase::password);
    }

    private static final ObjectMapper JSON = new ObjectMapper();

    @Autowired
    private ApplicationContext context;

    @Autowired
    private MockMvc mockMvc;

    @Test
    @DisplayName("仅 local profile：生效 profiles 恰为 local，登录/身份/设备/存储替身全部装配")
    void localProfileAssemblesFullProviderStack() {
        assertThat(context.getEnvironment().getActiveProfiles()).containsExactly("local");

        assertInstanceOf(InMemorySessionDouble.class, context.getBean(SessionProvider.class));
        assertInstanceOf(SmsCodeDouble.class, context.getBean(SmsCodeProvider.class));
        assertInstanceOf(DeviceCredentialDouble.class, context.getBean(DeviceCredentialProvider.class));
        assertInstanceOf(FaceProviderDouble.class, context.getBean(FaceProvider.class));
        assertInstanceOf(FileSystemStorageDouble.class, context.getBean(StoragePort.class));
        assertInstanceOf(DevTestDoublePairingProofVerifier.class,
                context.getBean(PairingProofVerifier.class));
        assertInstanceOf(DevTestDoubleConnectionProofVerifier.class,
                context.getBean(ConnectionProofVerifier.class));
        assertInstanceOf(DevTestFaceIdentityResolver.class, context.getBean(FaceIdentityResolver.class));

        // 护理人脸核验：@Primary 替身胜出，绝不是 FailClosedCareFaceVerifier（否则 local 下
        // 护理准入恒 503，功能退化）。
        CareFaceVerifier careFaceVerifier = context.getBean(CareFaceVerifier.class);
        assertInstanceOf(MemberBindingFaceDouble.class, careFaceVerifier);
        assertThat(careFaceVerifier).isNotInstanceOf(FailClosedCareFaceVerifier.class);
    }

    @Test
    @DisplayName("仅 local profile：固定验证码 123456 的登录链路真实可用（非启动失败/500）")
    void localProfileServesSmsLoginFlow() throws Exception {
        MvcResult challenge = mockMvc.perform(post("/api/v1/auth/sms-challenges")
                        .contentType("application/json")
                        .content("{\"phone\":\"+8613912345678\",\"purpose\":\"login\"}"))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode challengeData = JSON.readTree(challenge.getResponse().getContentAsString()).path("data");
        String challengeId = challengeData.path("challengeId").asText();

        MvcResult session = mockMvc.perform(post("/api/v1/auth/sessions")
                        .contentType("application/json")
                        .content("{\"challengeId\":\"" + challengeId
                                + "\",\"code\":\"123456\",\"installationId\":\"local-inst-0001\"}"))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode sessionData = JSON.readTree(session.getResponse().getContentAsString()).path("data");
        assertThat(sessionData.path("accessToken").asText()).isNotBlank();
        assertThat(sessionData.path("accountId").asText()).isNotBlank();
    }
}

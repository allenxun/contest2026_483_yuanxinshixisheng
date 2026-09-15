package cn.yuanxin.mvp.web.gimbalai;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link GimbalAiProvidersConfig} 装配优先级与 fail-closed 语义（纯工厂，不启动 web/PG）。
 */
class GimbalAiProvidersConfigTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private static GimbalAiProperties configured() {
        return new GimbalAiProperties("http://127.0.0.1:1", "TEST-API-KEY-PLACEHOLDER", 3000, 10000);
    }

    @Test
    @DisplayName("mode=disabled 优先：即使配置齐备也返回停机占位（503 DEPENDENCY_UNAVAILABLE）")
    void disabledWins() {
        MockEnvironment env = new MockEnvironment().withProperty("app.providers.mode", "disabled");
        GimbalAiClient client = GimbalAiProvidersConfig.createClient(configured(), env, mapper);

        assertThatThrownBy(() -> client.openStream("hi"))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    @Test
    @DisplayName("非生产 + 配置缺失 → 停机占位（运行时 503，不启动失败）")
    void missingConfigNonProductionIsRuntimeUnavailable() {
        MockEnvironment env = new MockEnvironment();
        GimbalAiClient client = GimbalAiProvidersConfig.createClient(new GimbalAiProperties("", "", null, null),
                env, mapper);

        assertThatThrownBy(() -> client.openStream("hi"))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    @Test
    @DisplayName("配置齐备且非 disabled → 真实 HttpGimbalAiClient")
    void configuredReturnsRealClient() {
        GimbalAiClient client = GimbalAiProvidersConfig.createClient(configured(),
                new MockEnvironment(), mapper);
        assertThat(client).isInstanceOf(HttpGimbalAiClient.class);
    }

    @Test
    @DisplayName("生产信号 + 配置缺失 → 启动失败（fail-closed，消息只列键名）")
    void productionMissingFailsClosed() {
        MockEnvironment env = new MockEnvironment().withProperty("app.env", "production");

        assertThatThrownBy(() -> GimbalAiProvidersConfig.createClient(
                new GimbalAiProperties("", "", null, null), env, mapper))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("production fail-closed")
                .hasMessageContaining("app.gimbal-ai.base-url")
                .hasMessageContaining("app.gimbal-ai.api-key");
    }

    @Test
    @DisplayName("prod profile + 配置缺失 → 同样启动失败")
    void prodProfileMissingFailsClosed() {
        MockEnvironment env = new MockEnvironment();
        env.setActiveProfiles("prod");

        assertThatThrownBy(() -> GimbalAiProvidersConfig.createClient(
                new GimbalAiProperties(null, null, null, null), env, mapper))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("production fail-closed");
    }

    @Test
    @DisplayName("生产信号但 mode=disabled → 停机占位（显式关闭能力允许启动）")
    void productionDisabledIsUnavailableNotFatal() {
        MockEnvironment env = new MockEnvironment()
                .withProperty("app.env", "production")
                .withProperty("app.providers.mode", "disabled");
        GimbalAiClient client = GimbalAiProvidersConfig.createClient(
                new GimbalAiProperties("", "", null, null), env, mapper);

        assertThatThrownBy(() -> client.openStream("hi"))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }
}

package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link ReportNarrationProvidersConfig} 装配优先级与 fail-closed 语义（纯工厂，不启动 web/PG）。
 */
class ReportNarrationProvidersConfigTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private static final ReportNarrationScores SCORES = new ReportNarrationScores(
            new ReportNarrationScores.ScoreGroup(new BigDecimal("61"), "mild", "毛孔",
                    List.of(new ReportNarrationScores.Region("F", "额头", new BigDecimal("40"), "ok"))),
            new ReportNarrationScores.ScoreGroup(new BigDecimal("55"), "moderate", "斑点",
                    List.of(new ReportNarrationScores.Region("L", "左脸", new BigDecimal("35"), "mild"))),
            new ReportNarrationScores.ScoreGroup(new BigDecimal("70"), "none", "光泽",
                    List.of(new ReportNarrationScores.Region("R", "右脸", new BigDecimal("82"), "good"))));

    private static ReportNarrationProperties configured() {
        return new ReportNarrationProperties(
                "http://127.0.0.1:1", ReportNarrationAiStub.FAKE_API_KEY, 3000, 30000);
    }

    @Test
    @DisplayName("mode=disabled 优先：即使配置齐备也返回停机占位（503 DEPENDENCY_UNAVAILABLE）")
    void disabledWins() {
        MockEnvironment env = new MockEnvironment().withProperty("app.providers.mode", "disabled");
        ReportNarrationClient client = ReportNarrationProvidersConfig.createClient(configured(), env, mapper);

        assertThatThrownBy(() -> client.openStream(SCORES))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    @Test
    @DisplayName("非生产 + 配置缺失 → 停机占位（运行时 503，不启动失败）")
    void missingConfigNonProductionIsRuntimeUnavailable() {
        MockEnvironment env = new MockEnvironment();
        ReportNarrationClient client = ReportNarrationProvidersConfig.createClient(
                new ReportNarrationProperties("", "", null, null), env, mapper);

        assertThatThrownBy(() -> client.openStream(SCORES))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }

    @Test
    @DisplayName("配置齐备且非 disabled → 真实 HttpReportNarrationClient")
    void configuredReturnsRealClient() {
        ReportNarrationClient client = ReportNarrationProvidersConfig.createClient(
                configured(), new MockEnvironment(), mapper);
        assertThat(client).isInstanceOf(HttpReportNarrationClient.class);
    }

    @Test
    @DisplayName("生产信号 + 配置缺失 → 启动失败（fail-closed，消息只列键名、不含值）")
    void productionMissingFailsClosed() {
        MockEnvironment env = new MockEnvironment().withProperty("app.env", "production");

        assertThatThrownBy(() -> ReportNarrationProvidersConfig.createClient(
                new ReportNarrationProperties("", "", null, null), env, mapper))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("production fail-closed")
                .hasMessageContaining("app.report-narration.base-url")
                .hasMessageContaining("app.report-narration.api-key")
                .hasMessageNotContaining(ReportNarrationAiStub.FAKE_API_KEY);
    }

    @Test
    @DisplayName("prod profile + 配置缺失 → 同样启动失败")
    void prodProfileMissingFailsClosed() {
        MockEnvironment env = new MockEnvironment();
        env.setActiveProfiles("prod");

        assertThatThrownBy(() -> ReportNarrationProvidersConfig.createClient(
                new ReportNarrationProperties(null, null, null, null), env, mapper))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("production fail-closed");
    }

    @Test
    @DisplayName("生产信号但 mode=disabled → 停机占位（显式关闭能力允许启动）")
    void productionDisabledIsUnavailableNotFatal() {
        MockEnvironment env = new MockEnvironment()
                .withProperty("app.env", "production")
                .withProperty("app.providers.mode", "disabled");
        ReportNarrationClient client = ReportNarrationProvidersConfig.createClient(
                new ReportNarrationProperties("", "", null, null), env, mapper);

        assertThatThrownBy(() -> client.openStream(SCORES))
                .isInstanceOf(ApiException.class)
                .satisfies(thrown -> assertThat(((ApiException) thrown).getCode())
                        .isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE));
    }
}

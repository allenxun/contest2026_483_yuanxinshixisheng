package cn.yuanxin.mvp.web.assessments.narration;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.config.NonProductionCondition;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import java.util.List;

/**
 * 报告播报客户端装配。优先级（与 B/C/D 既有 provider 约定一致）：
 * <pre>app.providers.mode=disabled （能力显式关闭） &gt; app.report-narration 配置是否齐备</pre>
 *
 * <ul>
 *   <li>{@code mode=disabled} → 停机占位：调用即 503 DEPENDENCY_UNAVAILABLE
 *       （沿 {@code DisabledProvidersConfig} 占位接线语义）；</li>
 *   <li>配置齐备 → 真实 {@link HttpReportNarrationClient}；</li>
 *   <li>配置缺失且<b>非生产</b> → 停机占位（运行时 503，应用仍可启动）；</li>
 *   <li>配置缺失且<b>生产信号</b>（{@code app.env=production} 或 prod profile）→
 *       启动失败（fail-closed；消息只列键名，绝不回显值）。</li>
 * </ul>
 *
 * <p>无替身回退：任何失败路径都不会产生合成文案。</p>
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiProvidersConfig} 同源范式、刻意不共享。</p>
 */
@Configuration
@EnableConfigurationProperties(ReportNarrationProperties.class)
public class ReportNarrationProvidersConfig {

    @Bean
    public ReportNarrationClient reportNarrationClient(ReportNarrationProperties properties,
                                                       Environment environment,
                                                       ObjectMapper objectMapper) {
        return createClient(properties, environment, objectMapper);
    }

    /**
     * 可单测的工厂：按 mode/env/配置选择真实客户端或停机占位。
     * 缺失键仅在消息中列键名，绝不回显值。
     */
    static ReportNarrationClient createClient(ReportNarrationProperties properties,
                                              Environment environment,
                                              ObjectMapper objectMapper) {
        String mode = new AppProperties.Providers(
                environment.getProperty("app.providers.mode")).mode();
        if ("disabled".equals(mode)) {
            return unavailable("report narration capability disabled by configuration");
        }
        List<String> missing = properties.missingRequiredKeys();
        if (missing.isEmpty()) {
            return new HttpReportNarrationClient(properties, objectMapper);
        }
        if (!NonProductionCondition.isNonProduction(environment)) {
            throw new IllegalStateException(
                    "production fail-closed: app.report-narration missing required config keys " + missing
                            + " (values are never logged); configure base-url/api-key or set"
                            + " app.providers.mode=disabled");
        }
        return unavailable("report narration capability is not configured");
    }

    private static ReportNarrationClient unavailable(String reason) {
        return scores -> {
            throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE, reason);
        };
    }
}

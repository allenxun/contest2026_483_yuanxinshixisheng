package cn.yuanxin.mvp.web.devices.proof;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * {@code app.providers.mode=disabled} 下 <b>B 自有</b>设备证明端口的显式关闭占位。
 *
 * <p>背景（既有缺口，本轮补齐）：A 的 {@code config/DisabledProvidersConfig} 只为
 * Session/Sms/DeviceCredential/Face/Storage 这 5 个 <b>A 端口</b>提供 disabled 占位；
 * 而 {@link PairingProofVerifier} 与 {@link ConnectionProofVerifier} 是 <b>B 自有端口</b>，
 * 分别被 {@code GimbalBindingService:48,52} 与 {@code MicrocrystalService:67,72}
 * <b>构造注入</b>（必需单例）。此前 {@code mode=disabled} 下唯一提供它们的
 * {@link DeviceProofDoublesConfig} 因 mode 门（{@code doubles}）不装配 ⇒ 完整应用
 * <b>根本无法启动</b>（实测失败于 {@code GimbalBindingService} 缺
 * {@code PairingProofVerifier}），与 {@code disabled} 的既定语义"能力显式关闭 →
 * 运行时 503 但仍可启动"相矛盾。本类补上这两个占位，使 {@code disabled} 成为
 * 一个真正可用、可验证的配置。</p>
 *
 * <p><b>为何抛 503 而不是返回 {@code Result.failed(...)}：</b>后者会被调用方解释为
 * "配对/连接证明无效"（403 类业务失败），那是把"能力被显式关闭"<b>误报成业务判定</b>。
 * 抛 {@link ErrorCode#DEPENDENCY_UNAVAILABLE}（HTTP 503、{@code retryable=true}）与 A 的
 * disabled 占位完全同风格（{@code "capability disabled by configuration: " + capability}），
 * 语义诚实且 fail closed——<b>绝不</b>降级为"证明有效"。</p>
 *
 * <p><b>刻意不加环境门</b>（与 A 的 {@code DisabledProvidersConfig} 对称）：本占位是
 * <b>抛错 fail-closed 桩、不是测试替身</b>，环境门对它没有安全价值；若加门，则
 * "{@code prod} profile + {@code app.env=dev} + {@code mode=disabled}"组合下会因缺 bean
 * 启动失败并把真因掩盖成"缺 bean"。生产安全不依赖本类：{@code app.env=production} 时
 * {@code ProductionFailClosedValidator} 会因 5 个 A 端口只有 doubles/disabled 占位而拒绝启动，
 * {@code DeviceProofFailClosedValidator} 另对证明端口做生产校验；{@code mode=doubles} +
 * 生产信号则由 {@code ProvidersModeProductionGuard} 早期明确拒绝。</p>
 *
 * <p>本类与 {@link DeviceProofDoublesConfig}（{@code mode=doubles}）由 mode <b>互斥</b>，
 * 不会同时装配；{@link DeviceConfig} 为空配置（仅注册 {@code DeviceProperties}），
 * 故无 bean 冲突。</p>
 */
@Configuration
@ConditionalOnProperty(name = "app.providers.mode", havingValue = "disabled")
public class DisabledDeviceProofVerifiersConfig {

    private static ApiException disabled(String capability) {
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "capability disabled by configuration: " + capability);
    }

    @Bean
    public PairingProofVerifier pairingProofVerifier() {
        return (proof, expectedGimbalId, accountId, installationId) -> {
            throw disabled("pairing-proof");
        };
    }

    @Bean
    public ConnectionProofVerifier connectionProofVerifier() {
        return (proof, principal, microcrystalSerial) -> {
            throw disabled("connection-proof");
        };
    }
}

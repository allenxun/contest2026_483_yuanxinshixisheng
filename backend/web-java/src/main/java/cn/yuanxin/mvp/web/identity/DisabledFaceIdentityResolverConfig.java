package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Optional;

/**
 * {@code app.providers.mode=disabled} 下 {@link FaceIdentityResolver} 的显式关闭占位
 * （B 自有 identity 包；<b>不改</b> A 的 {@code config/DisabledProvidersConfig}）。
 *
 * <p>背景：A 的 {@code DisabledProvidersConfig} 只为 Session/Sms/DeviceCredential/
 * Face/Storage 提供 disabled 占位，对 {@link FaceIdentityResolver} 命中数为 0；而本
 * 端口<b>没有 fail-closed 实现</b>且被 {@code MemberAccessGrantService} 构造注入（必需
 * 单例）。若只给 {@link IdentityProvidersConfig} 补 {@code mode=doubles} 门，则
 * {@code mode=disabled} 下将无 bean、上下文启动失败，破坏“disabled = 能力显式关闭 →
 * 运行时 503 但仍可启动”的既有语义。故在此补一个与 {@code DisabledProvidersConfig}
 * 同风格的占位：上下文可启动，相关端点运行时返回
 * {@code 503 DEPENDENCY_UNAVAILABLE} 信封。</p>
 *
 * <p>与 {@link DevTestFaceIdentityResolver} 的边界一致：本占位<b>绝不</b>伪造任何
 * “可靠匹配/新成员”结论——{@link FaceIdentityResolver#resolve} 与
 * {@link FaceIdentityResolver#identityNamespace} 一律抛错。</p>
 *
 * <p><b>刻意不加环境门（与 A 的 {@code DisabledProvidersConfig} 对称）。</b>本类只由
 * {@code app.providers.mode=disabled} 决定，<b>不</b>叠加 {@code NonProductionCondition}：
 * 本占位是<b>抛错 fail-closed 桩、不是测试替身</b>，环境门对它没有任何安全价值；反而会
 * 制造不对称——A 的 5 个 disabled 占位无环境门故在任何 profile 下都装配，而本占位若加门，
 * 则“{@code prod} profile + {@code app.env=dev} + {@code mode=disabled}”这一组合下会因缺
 * {@link FaceIdentityResolver} 而启动失败，并把真因掩盖成“缺 bean”（正是
 * {@code ProvidersModeProductionGuard} 要消除的那类诊断问题）。去掉环境门后该组合可正常启动、
 * 相关能力统一 503，与 {@code disabled} 的既定语义一致。</p>
 *
 * <p>生产安全不依赖本类的环境门：{@code app.env=production} 时
 * {@code ProductionFailClosedValidator} 会因 A 的 5 个端口只有 doubles/disabled 占位
 * （其 {@code isDouble()} 把 {@code DisabledProvidersConfig} 内的匿名类判为 double）而拒绝启动；
 * {@code mode=doubles} + 生产信号则由 {@code ProvidersModeProductionGuard} 早期明确拒绝。
 * 本类与 {@link IdentityProvidersConfig}（{@code mode=doubles}）由 mode <b>互斥</b>，不会同时装配。</p>
 */
@Configuration
@ConditionalOnProperty(name = "app.providers.mode", havingValue = "disabled")
public class DisabledFaceIdentityResolverConfig {

    private static ApiException disabled() {
        return new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "capability disabled by configuration: face-identity");
    }

    @Bean
    public FaceIdentityResolver faceIdentityResolver() {
        return new FaceIdentityResolver() {
            @Override
            public String identityNamespace() {
                throw disabled();
            }

            @Override
            public Optional<ResolvedFaceIdentity> resolve(byte[] content,
                                                          FaceClassification classification) {
                throw disabled();
            }
        };
    }
}

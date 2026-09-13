package cn.yuanxin.mvp.web.devices.proof;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@code app.providers.mode=disabled} 下 B 自有设备证明端口占位的装配与行为。
 *
 * <p>覆盖此前无法启动完整应用的既有缺口：{@code mode=disabled} 时
 * {@link DeviceProofDoublesConfig} 因 mode 门不装配，而 A 的
 * {@code DisabledProvidersConfig} 不覆盖这两个 <b>B 自有</b>端口 ⇒
 * {@code GimbalBindingService:48,52} / {@code MicrocrystalService:67,72} 构造注入失败
 * （实测失败信息为 "Parameter 3 of constructor in …GimbalBindingService required a bean of
 * type '…PairingProofVerifier' that could not be found"）。本类锁定补齐后的语义：
 * 两个端口都有占位、占位一律 503 {@code DEPENDENCY_UNAVAILABLE}、且<b>绝不</b>返回
 * "证明有效"（那会把"能力关闭"误报成业务判定通过）。</p>
 *
 * <p>本类为隔离上下文 runner，不连库、不启 web 服务器；完整应用可启动性由
 * orchestrator 的真实进程证据承担（{@code SPRING_PROFILES_ACTIVE=local} +
 * {@code --app.providers.mode=disabled} → UP、health 200）。</p>
 */
class DisabledDeviceProofVerifiersConfigTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(DisabledDeviceProofVerifiersConfig.class);

    /** 真实构造一个 APP 主体（占位实现不读取入参，但用真实类型锁定签名可用性）。 */
    private static PrincipalContext appPrincipal() {
        return new PrincipalContext(PrincipalType.APP, UUID.randomUUID(), "inst-1",
                null, 0L, "sess-1", "req-1");
    }

    @Test
    @DisplayName("mode=disabled：两个证明端口均装配为占位（不再缺 bean）")
    void disabledAssemblesBothVerifierPlaceholders() {
        runner.withPropertyValues("app.providers.mode=disabled")
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx).hasSingleBean(PairingProofVerifier.class);
                    assertThat(ctx).hasSingleBean(ConnectionProofVerifier.class);
                });
    }

    @Test
    @DisplayName("mode=disabled：占位一律抛 503 DEPENDENCY_UNAVAILABLE，绝不返回“证明有效”")
    void disabledPlaceholdersThrow503AndNeverValidate() {
        runner.withPropertyValues("app.providers.mode=disabled")
                .run(ctx -> {
                    PairingProofVerifier pairing = ctx.getBean(PairingProofVerifier.class);
                    assertThatThrownBy(() -> pairing.verify("any-proof", UUID.randomUUID(),
                            UUID.randomUUID(), "inst-1"))
                            .isInstanceOfSatisfying(ApiException.class, e -> {
                                assertThat(e.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
                                assertThat(e.getHttpStatus()).isEqualTo(503);
                                assertThat(e.getMessage()).contains("capability disabled by configuration")
                                        .contains("pairing-proof");
                            });

                    ConnectionProofVerifier connection = ctx.getBean(ConnectionProofVerifier.class);
                    assertThatThrownBy(() -> connection.verify("any-proof", appPrincipal(), "mc-1"))
                            .isInstanceOfSatisfying(ApiException.class, e -> {
                                assertThat(e.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
                                assertThat(e.getHttpStatus()).isEqualTo(503);
                                assertThat(e.getMessage()).contains("capability disabled by configuration")
                                        .contains("connection-proof");
                            });
                });
    }

    @Test
    @DisplayName("mode 非 disabled（doubles/缺省）：本占位不装配，不与替身配置争用")
    void notAssembledOutsideDisabledMode() {
        runner.withPropertyValues("app.providers.mode=doubles")
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    assertThat(ctx).doesNotHaveBean(PairingProofVerifier.class);
                    assertThat(ctx).doesNotHaveBean(ConnectionProofVerifier.class);
                });
        // 缺省（未配置 mode）⇒ matchIfMissing 语义属替身配置一侧，本占位仍不装配
        runner.run(ctx -> {
            assertThat(ctx).hasNotFailed();
            assertThat(ctx).doesNotHaveBean(PairingProofVerifier.class);
            assertThat(ctx).doesNotHaveBean(ConnectionProofVerifier.class);
        });
    }
}

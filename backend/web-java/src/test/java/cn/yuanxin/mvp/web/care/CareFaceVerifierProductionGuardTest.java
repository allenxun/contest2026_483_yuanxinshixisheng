package cn.yuanxin.mvp.web.care;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * BLOCKER-3：混合 profile / 生产上下文绝不选中成员绑定替身。
 * 防线一 {@link CareDevTestCondition}（组件选择）+ 防线二
 * {@link CareFaceVerifierProductionGuard}（启动 fail-fast），含纯单元与容器级证据。
 */
class CareFaceVerifierProductionGuardTest {

    private static MockEnvironment env(String appEnv, String... activeProfiles) {
        MockEnvironment environment = new MockEnvironment();
        if (appEnv != null) {
            environment.setProperty("app.env", appEnv);
        }
        environment.setActiveProfiles(activeProfiles);
        return environment;
    }

    @Test
    @DisplayName("生产 env + MemberBindingFaceDouble → 启动 fail-fast")
    void productionWithDoubleFailsFast() {
        CareFaceVerifierProductionGuard guard = new CareFaceVerifierProductionGuard(
                env("production"), new MemberBindingFaceDouble(UUID.randomUUID().toString()));
        assertThrows(IllegalStateException.class, guard::afterPropertiesSet);
    }

    @Test
    @DisplayName("仅 prod profile（app.env=dev）+ 替身 → 也 fail-fast")
    void prodProfileWithDoubleFailsFast() {
        CareFaceVerifierProductionGuard guard = new CareFaceVerifierProductionGuard(
                env("dev", "prod", "dev"), new MemberBindingFaceDouble(""));
        assertThrows(IllegalStateException.class, guard::afterPropertiesSet);
    }

    @Test
    @DisplayName("生产 env + FailClosedCareFaceVerifier → 通过；dev + 替身 → no-op")
    void guardPassesWhenExpected() {
        assertDoesNotThrow(() -> new CareFaceVerifierProductionGuard(env("production"),
                new FailClosedCareFaceVerifier()).afterPropertiesSet());
        assertDoesNotThrow(() -> new CareFaceVerifierProductionGuard(env("dev", "dev"),
                new MemberBindingFaceDouble("")).afterPropertiesSet());
    }

    @Test
    @DisplayName("容器级证据：profiles=prod,dev + 环境绑定 → 选中 FailClosed，绝不选中替身")
    void mixedProfileContextNeverSelectsDouble() {
        UUID configuredMember = UUID.randomUUID();
        try (AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().setActiveProfiles("prod", "dev");
            Map<String, Object> properties = new HashMap<>();
            properties.put("app.env", "production");
            properties.put("APP_C_FACE_BOUND_MEMBER", configuredMember.toString());
            context.getEnvironment().getPropertySources()
                    .addFirst(new MapPropertySource("mixed-profile", properties));
            context.register(FailClosedCareFaceVerifier.class, MemberBindingFaceDouble.class,
                    CareFaceVerifierProductionGuard.class);
            context.refresh();

            CareFaceVerifier selected = context.getBean(CareFaceVerifier.class);
            assertInstanceOf(FailClosedCareFaceVerifier.class, selected);
            assertFalse(selected instanceof MemberBindingFaceDouble);
        }
    }

    @Test
    @DisplayName("反向对照：dev 上下文 + 环境绑定 → 选中替身并对配置成员 MATCHED")
    void devContextSelectsConfiguredDouble() {
        UUID configuredMember = UUID.randomUUID();
        try (AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().setActiveProfiles("dev");
            Map<String, Object> properties = new HashMap<>();
            properties.put("app.env", "dev");
            properties.put("APP_C_FACE_BOUND_MEMBER", configuredMember.toString());
            context.getEnvironment().getPropertySources()
                    .addFirst(new MapPropertySource("dev-profile", properties));
            context.register(FailClosedCareFaceVerifier.class, MemberBindingFaceDouble.class,
                    CareFaceVerifierProductionGuard.class);
            context.refresh();

            CareFaceVerifier selected = context.getBean(CareFaceVerifier.class);
            assertInstanceOf(MemberBindingFaceDouble.class, selected);
            assertEquals(CareFaceVerifier.Outcome.MATCHED,
                    selected.verifyOneToOne("admission", configuredMember, new byte[]{1}));
        }
    }
}

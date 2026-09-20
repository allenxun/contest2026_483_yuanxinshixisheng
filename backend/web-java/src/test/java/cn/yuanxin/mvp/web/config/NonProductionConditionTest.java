package cn.yuanxin.mvp.web.config;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link NonProductionCondition} 纯单元测试（{@link MockEnvironment}，无 Spring 上下文、
 * 不连库）：锁定“环境 profile”与“实现选择”解耦后的非生产判据。
 */
class NonProductionConditionTest {

    /** 显式 active profiles。 */
    private static MockEnvironment active(String appEnv, String... activeProfiles) {
        MockEnvironment environment = new MockEnvironment();
        if (appEnv != null) {
            environment.setProperty("app.env", appEnv);
        }
        environment.setActiveProfiles(activeProfiles);
        return environment;
    }

    /** 无显式 active profile；default profiles 模拟 application.yml 的 {@code dev}。 */
    private static MockEnvironment defaultOnly(String appEnv, String... defaultProfiles) {
        MockEnvironment environment = new MockEnvironment();
        if (appEnv != null) {
            environment.setProperty("app.env", appEnv);
        }
        environment.setDefaultProfiles(defaultProfiles);
        return environment;
    }

    // ---------- 放行：任何非生产环境名 ----------

    @Test
    @DisplayName("local/dev/test 环境放行")
    void localDevTestAreNonProduction() {
        assertTrue(NonProductionCondition.isNonProduction(active("dev", "local")));
        assertTrue(NonProductionCondition.isNonProduction(active("dev", "dev")));
        assertTrue(NonProductionCondition.isNonProduction(active("test", "test")));
    }

    @Test
    @DisplayName("无显式 profile（default=dev）放行")
    void defaultDevProfileIsNonProduction() {
        assertTrue(NonProductionCondition.isNonProduction(defaultOnly(null, "dev")));
    }

    @Test
    @DisplayName("app.env 缺省（默认 dev）放行")
    void missingAppEnvDefaultsToDev() {
        assertTrue(NonProductionCondition.isNonProduction(active(null, "local")));
    }

    @Test
    @DisplayName("自定义环境名（staging/anything）放行——不要求 dev/test")
    void customEnvironmentNamesAreNonProduction() {
        assertTrue(NonProductionCondition.isNonProduction(active("staging", "staging")));
        assertTrue(NonProductionCondition.isNonProduction(active("qa", "anything")));
    }

    // ---------- 拒绝：生产 env / prod profile / 混合 ----------

    @Test
    @DisplayName("prod / production profile 拒绝")
    void prodProfilesAreProduction() {
        assertFalse(NonProductionCondition.isNonProduction(active("dev", "prod")));
        assertFalse(NonProductionCondition.isNonProduction(active("dev", "production")));
    }

    @Test
    @DisplayName("混合 prod,dev 与 dev,prod 均拒绝（不因含 dev 而放行）")
    void mixedProdDevProfilesAreProduction() {
        assertFalse(NonProductionCondition.isNonProduction(active("dev", "prod", "dev")));
        assertFalse(NonProductionCondition.isNonProduction(active("dev", "dev", "prod")));
    }

    @Test
    @DisplayName("app.env=production + dev profile 拒绝（env 判据独立生效）")
    void productionEnvWithDevProfileIsProduction() {
        assertFalse(NonProductionCondition.isNonProduction(active("production", "dev")));
    }

    @Test
    @DisplayName("app.env=' Production '（大小写/空白）拒绝")
    void productionEnvCaseInsensitiveAndTrimmed() {
        assertFalse(NonProductionCondition.isNonProduction(active(" Production ", "local")));
    }

    @Test
    @DisplayName("app.env=dev + prod profile 拒绝（profile 判据独立生效）")
    void prodProfileWithDevEnvIsProduction() {
        assertFalse(NonProductionCondition.isNonProduction(active("dev", "prod")));
    }

    // ---------- effectiveProfiles 语义 ----------

    @Test
    @DisplayName("effectiveProfiles：active 非空时优先，忽略 default")
    void effectiveProfilesPreferActive() {
        MockEnvironment environment = defaultOnly(null, "prod");
        environment.setActiveProfiles("local");
        assertEquals(Set.of("local"), NonProductionCondition.effectiveProfiles(environment));
        assertTrue(NonProductionCondition.isNonProduction(environment));
    }

    @Test
    @DisplayName("effectiveProfiles：active 为空则取 default，统一小写")
    void effectiveProfilesFallBackToDefault() {
        MockEnvironment environment = defaultOnly(null, "Dev", "TEST");
        assertEquals(Set.of("dev", "test"), NonProductionCondition.effectiveProfiles(environment));
    }

    @Test
    @DisplayName("effectiveProfiles：active 统一小写（PROD → prod）")
    void effectiveProfilesLowercase() {
        MockEnvironment environment = active("dev", "PROD");
        assertEquals(Set.of("prod"), NonProductionCondition.effectiveProfiles(environment));
        assertFalse(NonProductionCondition.isNonProduction(environment));
    }
}

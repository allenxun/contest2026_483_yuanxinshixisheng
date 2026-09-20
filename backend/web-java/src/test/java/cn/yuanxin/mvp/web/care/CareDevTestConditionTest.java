package cn.yuanxin.mvp.web.care;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ResourceLoader;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** {@link CareDevTestCondition} 纯单元测试（MockEnvironment，无 Spring 上下文）。 */
class CareDevTestConditionTest {

    private static boolean matches(String appEnv, String... activeProfiles) {
        MockEnvironment environment = new MockEnvironment();
        if (appEnv != null) {
            environment.setProperty("app.env", appEnv);
        }
        environment.setActiveProfiles(activeProfiles);
        return new CareDevTestCondition().matches(context(environment), null);
    }

    private static ConditionContext context(Environment environment) {
        return new ConditionContext() {
            @Override
            public BeanDefinitionRegistry getRegistry() {
                return null;
            }

            @Override
            public ConfigurableListableBeanFactory getBeanFactory() {
                return null;
            }

            @Override
            public Environment getEnvironment() {
                return environment;
            }

            @Override
            public ResourceLoader getResourceLoader() {
                return null;
            }

            @Override
            public ClassLoader getClassLoader() {
                return CareDevTestConditionTest.class.getClassLoader();
            }
        };
    }

    @Test
    @DisplayName("[dev] 与 [test] 生效；混合 prod/production 或空 profile 不生效")
    void profileMatrix() {
        assertTrue(matches("dev", "dev"));
        assertTrue(matches("test", "test"));
        assertFalse(matches("dev", "prod", "dev"));
        assertFalse(matches("dev", "production", "dev"));
        assertFalse(matches("dev"));
        assertFalse(matches("production", "dev"));
    }
}

package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.SessionProvider;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

import java.lang.reflect.Method;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

/**
 * 装配与守卫测试（不需 Redis）：{@code app.state.provider=redis} 缺连接配置 / 非法取值 /
 * 生产 + {@code mode=real} + memory 均被 {@link StateStoreConfigGuard} 拒绝；
 * 生产 + {@code mode=disabled} 不被本守卫拒绝；{@code provider=redis}+{@code mode=real}+生产
 * 时 {@link SessionProvider} 是 {@link RedisSessionProvider} 且不是替身。
 */
class RedisSessionConfigGuardTest {

    @Configuration
    @EnableConfigurationProperties(AppStateProperties.class)
    static class PropsConfig {
    }

    @Configuration
    static class MockInfra {
        @Bean
        StringRedisTemplate stringRedisTemplate() {
            return mock(StringRedisTemplate.class);
        }

        @Bean
        JdbcTemplate jdbcTemplate() {
            return mock(JdbcTemplate.class);
        }
    }

    private static ApplicationContextRunner guardOnly() {
        return new ApplicationContextRunner()
                .withUserConfiguration(StateStoreConfigGuard.class, PropsConfig.class);
    }

    @Test
    @DisplayName("provider=redis 但无任何 spring.data.redis.* 连接属性 ⇒ 拒绝启动（只含键名）")
    void redisWithoutConnectionRefusesStartup() {
        guardOnly().withPropertyValues("app.state.provider=redis").run(ctx -> {
            assertThat(ctx).hasFailed();
            assertThat(ctx.getStartupFailure())
                    .hasMessageContaining("app.state.provider")
                    .hasMessageContaining("spring.data.redis.host")
                    .hasMessageContaining("values are never logged");
        });
    }

    @Test
    @DisplayName("非法 provider 取值 ⇒ 拒绝启动（不 fallback 到 memory）")
    void invalidProviderRefusesStartup() {
        guardOnly().withPropertyValues("app.state.provider=bogus").run(ctx -> {
            assertThat(ctx).hasFailed();
            assertThat(ctx.getStartupFailure())
                    .hasMessageContaining("invalid app.state.provider")
                    .hasMessageContaining("redis");
        });
    }

    @Test
    @DisplayName("生产信号 + mode=real + provider=memory ⇒ 拒绝启动")
    void productionRealWithMemoryRefusesStartup() {
        guardOnly()
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles("prod"))
                .withPropertyValues("app.providers.mode=real")
                .run(ctx -> {
                    assertThat(ctx).hasFailed();
                    assertThat(ctx.getStartupFailure())
                            .hasMessageContaining("app.state.provider")
                            .hasMessageContaining("app.providers.mode=real");
                });
    }

    @Test
    @DisplayName("生产信号 + mode=disabled + provider=memory ⇒ 不被本守卫拒绝")
    void productionDisabledWithMemoryAllowed() {
        guardOnly()
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles("prod"))
                .withPropertyValues("app.providers.mode=disabled")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }

    @Test
    @DisplayName("provider=redis + 有连接属性 ⇒ 守卫通过（运行期才连接）")
    void redisWithConnectionPassesGuard() {
        guardOnly()
                .withPropertyValues("app.state.provider=redis", "spring.data.redis.host=127.0.0.1")
                .run(ctx -> assertThat(ctx).hasNotFailed());
    }

    @Test
    @DisplayName("生产+real+redis：SessionProvider 是 RedisSessionProvider 且被判为 real（非替身）")
    void redisProviderIsRealUnderProduction() throws Exception {
        new ApplicationContextRunner()
                .withUserConfiguration(PropsConfig.class, MockInfra.class,
                        RedisStateConfig.class, RedisSessionConfig.class)
                .withInitializer(ctx -> ctx.getEnvironment().setActiveProfiles("prod"))
                .withPropertyValues(
                        "app.state.provider=redis",
                        "app.state.redis.key-prefix=b-config-guard-",
                        "app.providers.mode=real",
                        "spring.data.redis.host=127.0.0.1")
                .run(ctx -> {
                    assertThat(ctx).hasNotFailed();
                    SessionProvider sessionProvider = ctx.getBean(SessionProvider.class);
                    assertThat(sessionProvider).isInstanceOf(RedisSessionProvider.class);
                    assertThat(isDouble(sessionProvider.getClass()))
                            .as("RedisSessionProvider must not be treated as a test double").isFalse();
                });
    }

    /** 以既有 package-private 判定为准（在 config 包外，用反射调用避免复制判据）。 */
    private static boolean isDouble(Class<?> clazz) throws Exception {
        Class<?> validator = Class.forName("cn.yuanxin.mvp.web.config.ProductionFailClosedValidator");
        Method method = validator.getDeclaredMethod("isDouble", Class.class);
        method.setAccessible(true);
        return (Boolean) method.invoke(null, clazz);
    }
}

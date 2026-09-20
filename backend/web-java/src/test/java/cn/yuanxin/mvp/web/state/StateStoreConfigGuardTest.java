package cn.yuanxin.mvp.web.state;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.mock.env.MockEnvironment;

import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * {@link StateStoreConfigGuard} 的<b>纯单元</b>测试：用 {@link MockEnvironment} +
 * {@link DefaultListableBeanFactory} 直接调 {@code postProcessBeanFactory}，不需要 Spring 上下文、
 * 不需要 Redis。重点覆盖"真实短信 provider 必须搭配 Redis，且<b>无</b>运行时逃生门"。
 */
class StateStoreConfigGuardTest {

    @Test
    @DisplayName("app.sms.provider=aliyun + provider 缺省(⇒memory) ⇒ 拒绝，消息含 app.state.provider=redis")
    void aliyunWithUnsetProviderRefuses() {
        IllegalStateException thrown = expectFailure(Map.of("app.sms.provider", "aliyun"));
        assertThat(thrown.getMessage())
                .contains("app.sms.provider=aliyun")
                .contains("app.state.provider=redis")
                .contains("values are never logged");
    }

    @Test
    @DisplayName("app.sms.provider=aliyun + provider=memory ⇒ 无条件拒绝")
    void aliyunWithMemoryRefuses() {
        IllegalStateException thrown = expectFailure(Map.of(
                "app.sms.provider", "aliyun",
                "app.state.provider", "memory"));
        assertThat(thrown.getMessage()).contains("app.state.provider=redis");
    }

    @Test
    @DisplayName("app.sms.provider=aliyun + provider=redis + 连接属性 ⇒ 放行")
    void aliyunWithRedisAndConnectionAllowed() {
        invoke(Map.of(
                "app.sms.provider", "aliyun",
                "app.state.provider", "redis",
                "spring.data.redis.host", "127.0.0.1"));
    }

    @Test
    @DisplayName("app.sms.provider=doubles + provider=memory ⇒ 放行（既有行为不变）")
    void doublesWithMemoryAllowed() {
        invoke(Map.of("app.sms.provider", "doubles", "app.state.provider", "memory"));
    }

    @Test
    @DisplayName("已删除运行时逃生门：StateStoreConfigGuard 不含任何 allow-in-memory-with-real-sms 字段")
    void noRuntimeEscapeHatchFieldExists() {
        List<String> fieldNames = Arrays.stream(StateStoreConfigGuard.class.getDeclaredFields())
                .map(Field::getName)
                .collect(Collectors.toList());
        assertThat(fieldNames)
                .doesNotContain("ALLOW_IN_MEMORY_WITH_REAL_SMS_KEY")
                .noneMatch(name -> name.toLowerCase(java.util.Locale.ROOT)
                        .contains("allowinmemorywithrealsms"));
        assertThat(fieldNames).noneMatch(name -> name.contains("allow-in-memory-with-real-sms"));
    }

    @Test
    @DisplayName("provider=redis 缺连接属性 ⇒ 拒绝（只含键名）")
    void redisMissingConnectionRefuses() {
        IllegalStateException thrown = expectFailure(Map.of("app.state.provider", "redis"));
        assertThat(thrown.getMessage())
                .contains("spring.data.redis.host")
                .contains("values are never logged");
    }

    @Test
    @DisplayName("非法 provider 取值 ⇒ 拒绝")
    void invalidProviderRefuses() {
        IllegalStateException thrown = expectFailure(Map.of("app.state.provider", "bogus"));
        assertThat(thrown.getMessage()).contains("invalid app.state.provider");
    }

    @Test
    @DisplayName("生产信号 + mode=real + memory ⇒ 拒绝（既有规则保留）")
    void productionRealMemoryRefuses() {
        StateStoreConfigGuard guard = new StateStoreConfigGuard();
        MockEnvironment environment = new MockEnvironment();
        environment.setActiveProfiles("prod");
        environment.setProperty("app.providers.mode", "real");
        guard.setEnvironment(environment);
        IllegalStateException thrown = null;
        try {
            guard.postProcessBeanFactory(new DefaultListableBeanFactory());
        } catch (IllegalStateException failure) {
            thrown = failure;
        }
        assertThat(thrown).isNotNull();
        assertThat(thrown.getMessage()).contains("app.state.provider");
    }

    @Test
    @DisplayName("生产信号 + mode=disabled + memory ⇒ 不拒绝（既有规则保留）")
    void productionDisabledMemoryAllowed() {
        StateStoreConfigGuard guard = new StateStoreConfigGuard();
        MockEnvironment environment = new MockEnvironment();
        environment.setActiveProfiles("prod");
        environment.setProperty("app.providers.mode", "disabled");
        guard.setEnvironment(environment);
        guard.postProcessBeanFactory(new DefaultListableBeanFactory());
    }

    // ---------- helpers ----------

    private static void invoke(Map<String, String> properties) {
        StateStoreConfigGuard guard = new StateStoreConfigGuard();
        MockEnvironment environment = new MockEnvironment();
        properties.forEach(environment::setProperty);
        guard.setEnvironment(environment);
        guard.postProcessBeanFactory(new DefaultListableBeanFactory());
    }

    private static IllegalStateException expectFailure(Map<String, String> properties) {
        StateStoreConfigGuard guard = new StateStoreConfigGuard();
        MockEnvironment environment = new MockEnvironment();
        new LinkedHashMap<>(properties).forEach(environment::setProperty);
        guard.setEnvironment(environment);
        IllegalStateException thrown = null;
        try {
            guard.postProcessBeanFactory(new DefaultListableBeanFactory());
        } catch (IllegalStateException failure) {
            thrown = failure;
        }
        assertThat(thrown).as("guard must refuse").isNotNull();
        return thrown;
    }
}

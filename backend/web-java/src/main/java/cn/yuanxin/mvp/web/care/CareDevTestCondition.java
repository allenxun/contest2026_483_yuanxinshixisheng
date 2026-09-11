package cn.yuanxin.mvp.web.care;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Environment;
import org.springframework.core.type.AnnotatedTypeMetadata;

import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * C 域 dev/test 组件选择条件（取代单纯 {@code @Profile}，防混合 profile 逃逸）。
 *
 * <p>仅当以下全部成立才匹配（C 侧防线一）：</p>
 * <ol>
 *   <li>{@code app.env != "production"}；</li>
 *   <li>生效 profiles 不含 {@code prod} 或 {@code production}；</li>
 *   <li>生效 profiles 含 {@code dev} 或 {@code test}。</li>
 * </ol>
 *
 * <p>“生效 profiles” = 显式 active profiles（非空时），否则取 default profiles
 * （application.yml 默认 {@code dev}）。这样 {@code SPRING_PROFILES_ACTIVE=prod,dev}
 * 之类的混合配置不会因含 {@code dev} 而放行测试替身。</p>
 */
public class CareDevTestCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        Environment environment = context.getEnvironment();
        if ("production".equalsIgnoreCase(environment.getProperty("app.env", "dev"))) {
            return false;
        }
        Set<String> profiles = effectiveProfiles(environment);
        if (profiles.contains("prod") || profiles.contains("production")) {
            return false;
        }
        return profiles.contains("dev") || profiles.contains("test");
    }

    /** 生效 profile（显式 active 优先，否则 default），统一小写。 */
    static Set<String> effectiveProfiles(Environment environment) {
        String[] active = environment.getActiveProfiles();
        String[] effective = active.length > 0 ? active : environment.getDefaultProfiles();
        Set<String> profiles = new HashSet<>();
        for (String profile : effective) {
            if (profile != null) {
                profiles.add(profile.toLowerCase(Locale.ROOT));
            }
        }
        return profiles;
    }
}

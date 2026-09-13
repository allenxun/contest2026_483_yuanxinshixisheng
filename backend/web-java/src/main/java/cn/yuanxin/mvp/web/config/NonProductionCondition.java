package cn.yuanxin.mvp.web.config;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Environment;
import org.springframework.core.type.AnnotatedTypeMetadata;

import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * “是否非生产环境”共享条件：把<b>环境 profile</b>与<b>{@code app.providers.mode} 服务实现选择</b>
 * 解耦后，所有 dev/test 替身配置统一改用本条件门。
 *
 * <p>设计意图：profile 表达“环境”（local/dev/test/staging/…），{@code app.providers.mode}
 * 表达“实现选择”（doubles/real/…）。本条件只回答“是否非生产环境”，具体实现选择仍由各配置
 * 自己的 {@code @ConditionalOnProperty(app.providers.mode=…)} 决定——因此本类<b>不</b>新增、
 * 删除或改变任何 mode 门。</p>
 *
 * <p>判据恰为两条（任何一条成立即视为生产 ⇒ 不匹配）：</p>
 * <ol>
 *   <li>{@code app.env}（默认 {@code "dev"}）{@code trim()} 后等于（忽略大小写）
 *       {@code production}；</li>
 *   <li>生效 profiles 含 {@code prod} 或 {@code production}（小写归一）。</li>
 * </ol>
 * <p>否则匹配。匹配<b>不要求</b> profile 是 {@code dev}/{@code test}：{@code local}、
 * 无显式 profile（此时取 default profiles）以及任何自定义环境名都放行。</p>
 *
 * <p>“生效 profiles”语义：显式 active profiles 非空时取之，否则取
 * {@link Environment#getDefaultProfiles()}（application.yml 默认 {@code dev}）；统一
 * {@link Locale#ROOT} 小写并跳过 {@code null}。因此 {@code SPRING_PROFILES_ACTIVE=prod,dev}
 * 这类混合配置不会因含 {@code dev} 而被放行；{@code app.env=dev} 也不能覆盖 {@code prod}
 * profile 信号（双判据，任一命中即拒绝）。</p>
 *
 * <p>日志/异常消息不使用本类输出；调用方如需说明可引用 profile 名与 {@code app.env}，
 * 不得输出数据源/凭据等敏感内容。</p>
 */
public class NonProductionCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        return isNonProduction(context.getEnvironment());
    }

    /**
     * 非生产环境判定（供 {@link #matches} 与本包/其它条件下游共用，避免逻辑重复）。
     *
     * @return {@code true} 当且仅当 {@code app.env != production} 且生效 profiles 不含
     *         {@code prod}/{@code production}
     */
    public static boolean isNonProduction(Environment environment) {
        if ("production".equalsIgnoreCase(environment.getProperty("app.env", "dev").trim())) {
            return false;
        }
        Set<String> profiles = effectiveProfiles(environment);
        return !profiles.contains("prod") && !profiles.contains("production");
    }

    /** 生效 profile（显式 active 优先，否则 default），统一小写、跳过 null。 */
    public static Set<String> effectiveProfiles(Environment environment) {
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

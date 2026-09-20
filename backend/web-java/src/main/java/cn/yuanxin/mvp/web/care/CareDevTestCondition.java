package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.config.NonProductionCondition;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Environment;
import org.springframework.core.type.AnnotatedTypeMetadata;

import java.util.Set;

/**
 * C 域 dev/test 组件选择条件（取代单纯 {@code @Profile}，防混合 profile 逃逸）。
 *
 * <p>仅当以下全部成立才匹配（C 侧防线一）：</p>
 * <ol>
 *   <li>非生产环境（委托 {@link NonProductionCondition#isNonProduction(Environment)}：
 *       {@code app.env != "production"} 且生效 profiles 不含 {@code prod}/{@code production}）；</li>
 *   <li>生效 profiles 含 {@code dev} 或 {@code test}。</li>
 * </ol>
 *
 * <p><b>本轮改造：</b>第 1 条“非生产环境”判据已抽出为共享的
 * {@link NonProductionCondition}（profile 表达环境、{@code app.providers.mode} 表达实现
 * 选择，二者解耦）；本条件只在其上<b>追加</b> C 域自有的第 2 条白名单（生效 profiles 必须
 * 含 dev/test）。</p>
 *
 * <p><b>与改造前的唯一行为差异（如实记录，方向为 fail-closed 增强）：</b>改造前本类对
 * {@code app.env} 的判定是 {@code "production".equalsIgnoreCase(getProperty("app.env","dev"))}
 * ——<b>不做 {@code trim()}</b>；委托后改用
 * {@link NonProductionCondition#isNonProduction(Environment)}，其对 {@code app.env}
 * {@code trim()} 后再忽略大小写比较，故 {@code app.env=" Production "} 这类带空白的取值
 * <b>现在也会被判为生产</b>（改造前会被放行）。其余判据（生效 profiles 的 active 优先/
 * default 回落、小写归一、prod/production 黑名单、dev/test 白名单）与改造前逐条一致。
 * 既有 {@code CareDevTestConditionTest} <b>未修改一行</b>且原样通过——它未覆盖带空白的
 * {@code app.env} 变体，故不能作为“零行为变化”的证明；该差异由本段与
 * {@code NonProductionConditionTest} 的 {@code " Production "} 用例共同记录。</p>
 *
 * <p>“生效 profiles” = 显式 active profiles（非空时），否则取 default profiles
 * （application.yml 默认 {@code dev}）。这样 {@code SPRING_PROFILES_ACTIVE=prod,dev}
 * 之类的混合配置不会因含 {@code dev} 而放行测试替身。</p>
 */
public class CareDevTestCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        Environment environment = context.getEnvironment();
        if (!NonProductionCondition.isNonProduction(environment)) {
            return false;
        }
        Set<String> profiles = effectiveProfiles(environment);
        return profiles.contains("dev") || profiles.contains("test");
    }

    /**
     * 生效 profile（显式 active 优先，否则 default），统一小写。
     *
     * <p>保留为 C 域静态入口：{@code CareFaceVerifierProductionGuard} 等既有调用方依赖它；
     * 实现委托 {@link NonProductionCondition#effectiveProfiles(Environment)}，语义一致。</p>
     */
    static Set<String> effectiveProfiles(Environment environment) {
        return NonProductionCondition.effectiveProfiles(environment);
    }
}

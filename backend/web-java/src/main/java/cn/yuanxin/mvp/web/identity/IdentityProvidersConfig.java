package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.config.NonProductionCondition;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

/**
 * M1 身份解析接线（B 自有配置，不改 A 的 config 包）。
 *
 * <p>仅在<b>非生产环境</b>且 <b>{@code app.providers.mode=doubles}</b>（默认，
 * {@code matchIfMissing=true}）时注册 {@link DevTestFaceIdentityResolver}：
 * 环境由 {@link NonProductionCondition} 门控（{@code app.env != production} 且
 * 生效 profiles 不含 prod/production；{@code local} 等自定义环境名同样装配），
 * 实现选择由 {@code @ConditionalOnProperty(app.providers.mode=doubles)} 门控
 * ——二者已解耦，环境不再隐式决定实现。</p>
 *
 * <p>生产或 {@code mode=real} 下无 {@link FaceIdentityResolver} bean → 需要它的
 * 单例（如 {@code MemberAccessGrantService}）注入失败 → 应用启动失败。这是
 * <b>既有且刻意</b>的 fail-closed：真实人脸供应商未接入时绝不伪造"可靠匹配"，
 * 不得视为缺陷去"修好"。{@code mode=disabled} 的显式关闭兜底见
 * {@code DisabledFaceIdentityResolverConfig}（B 自有，仍可启动并在运行时 503）。</p>
 *
 * <p>身份命名空间默认值仅联调用，经 {@code app.identity.namespace} 覆盖。</p>
 */
@Configuration
@Conditional(NonProductionCondition.class)
@ConditionalOnProperty(name = "app.providers.mode", havingValue = "doubles", matchIfMissing = true)
public class IdentityProvidersConfig {

    @Bean
    public FaceIdentityResolver faceIdentityResolver(
            @Value("${app.identity.namespace:mvp-local}") String namespace) {
        return new DevTestFaceIdentityResolver(namespace);
    }
}

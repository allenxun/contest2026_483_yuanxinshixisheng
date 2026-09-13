package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.config.NonProductionCondition;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

/**
 * M1 身份解析接线（B 自有配置，不改 A 的 config 包）。
 *
 * <p>仅在<b>非生产环境</b>注册 {@link DevTestFaceIdentityResolver}
 * （{@link NonProductionCondition}：{@code app.env != production} 且生效
 * profiles 不含 prod/production；{@code local} 等自定义环境名同样装配）。
 * 生产（{@code app.env=production} 或生效 profiles 含 prod/production）无
 * {@link FaceIdentityResolver} bean → 业务控制器注入失败 → 应用启动失败
 * （fail closed：真实人脸供应商未接入时绝不伪造"可靠匹配"）。</p>
 *
 * <p>本配置<b>只有环境条件、没有 mode 门</b>，这是既有语义：非生产环境下即便
 * {@code app.providers.mode=real}，本替身仍会装配。本轮只做环境解耦，未改变该行为。</p>
 *
 * <p>身份命名空间默认值仅联调用，经 {@code app.identity.namespace} 覆盖。</p>
 */
@Configuration
@Conditional(NonProductionCondition.class)
public class IdentityProvidersConfig {

    @Bean
    public FaceIdentityResolver faceIdentityResolver(
            @Value("${app.identity.namespace:mvp-local}") String namespace) {
        return new DevTestFaceIdentityResolver(namespace);
    }
}

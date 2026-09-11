package cn.yuanxin.mvp.web.identity;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

/**
 * M1 身份解析接线（B 自有配置，不改 A 的 config 包）。
 *
 * <p>仅在 dev/test profile 注册 {@link DevTestFaceIdentityResolver}。生产
 * （prod profile / app.providers.mode=real）无 {@link FaceIdentityResolver}
 * bean → 业务控制器注入失败 → 应用启动失败（fail closed：真实人脸供应商未
 * 接入时绝不伪造"可靠匹配"）。</p>
 *
 * <p>身份命名空间默认值仅联调用，经 {@code app.identity.namespace} 覆盖。</p>
 */
@Configuration
@Profile({"dev", "test"})
public class IdentityProvidersConfig {

    @Bean
    public FaceIdentityResolver faceIdentityResolver(
            @Value("${app.identity.namespace:mvp-local}") String namespace) {
        return new DevTestFaceIdentityResolver(namespace);
    }
}

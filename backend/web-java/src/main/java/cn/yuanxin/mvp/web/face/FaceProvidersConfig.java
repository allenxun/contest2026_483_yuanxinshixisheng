package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.auth.FaceProvider;
import cn.yuanxin.mvp.web.care.CareFaceVerifier;
import cn.yuanxin.mvp.web.config.NonProductionCondition;
import cn.yuanxin.mvp.web.identity.FaceIdentityResolver;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;

/**
 * InsightFace 人脸装配（B 自有）：仅当 {@code app.face.provider=insightface} <b>且</b>
 * {@code app.providers.mode != disabled} 时激活。
 *
 * <p><b>启动期校验</b>：缺 {@code base-url}/{@code namespace}/token（二选一皆无）⇒ 拒绝启动，
 * 消息只列缺失键名；内联 token 与 token 文件同时配置 ⇒ 拒绝启动（歧义）。<b>不调用远端服务
 * 校验配置</b>（避免启动期网络依赖与副作用）。</p>
 *
 * <p><b>装配</b>：{@link InsightFaceProvider}（FaceProvider，真实；可生产）、
 * {@link UnavailableFaceIdentityResolver}（红线 2：身份解析未接入，恒 empty）、
 * {@link InsightFaceCareVerifier}（{@code @Primary}；<b>非生产条件</b>——生产信号下不装配，
 * 由无条件 {@code FailClosedCareFaceVerifier} 接管，避免与
 * {@code CareFaceVerifierProductionGuard} 冲突；守卫未改）。</p>
 *
 * <p>{@code mode=disabled} 时本配置整体不激活，走 A 的 disabled 占位。</p>
 */
@Configuration
@ConditionalOnProperty(name = "app.face.provider", havingValue = "insightface")
@Conditional(FaceProviderEnabledCondition.class)
@EnableConfigurationProperties({InsightFaceProperties.class, AliyunFaceProperties.class})
public class FaceProvidersConfig {

    @Bean
    public FaceServiceClient faceServiceClient(InsightFaceProperties properties,
                                               ObjectMapper objectMapper) {
        List<String> missing = properties.missingRequiredKeys();
        if (!missing.isEmpty()) {
            throw new IllegalStateException("app.face.provider=insightface missing required config keys: "
                    + missing + " (values are never logged)");
        }
        if (properties.tokenSourcesConflict()) {
            throw new IllegalStateException("app.face.provider=insightface requires exactly one of"
                    + " internal-token / internal-token-file (both are set)");
        }
        return new FaceServiceClient(properties, objectMapper);
    }

    @Bean
    public FaceProvider insightFaceProvider(FaceServiceClient faceServiceClient) {
        return new InsightFaceProvider(faceServiceClient);
    }

    @Bean
    public FaceIdentityResolver unavailableFaceIdentityResolver(InsightFaceProperties properties) {
        return new UnavailableFaceIdentityResolver(properties.namespace());
    }

    /** 非生产条件：生产信号下不装配，避免与 {@code CareFaceVerifierProductionGuard} 冲突。 */
    @Bean
    @Conditional(NonProductionCondition.class)
    @Primary
    public CareFaceVerifier insightFaceCareVerifier(FaceServiceClient faceServiceClient,
                                                    JdbcTemplate jdbc,
                                                    InsightFaceProperties properties) {
        return new InsightFaceCareVerifier(faceServiceClient, jdbc, properties.verifyThreshold());
    }
}

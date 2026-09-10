package cn.yuanxin.mvp.web.config;

import cn.yuanxin.mvp.web.auth.PrincipalContextArgumentResolver;
import cn.yuanxin.mvp.web.media.AllowAuthenticatedMediaAccessPolicy;
import cn.yuanxin.mvp.web.media.MediaAccessPolicy;
import com.fasterxml.jackson.core.JsonParser;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.List;

/**
 * 基础接线：配置属性、Jackson 严格解析（重复 JSON 键拒绝——JCS/canonicalization
 * 前提）、TransactionTemplate（业务写 + T13/T12 同事务提交的载体）、
 * PrincipalContext 参数解析器、媒体授权 dev 默认（B/C/D @Primary 覆盖点）。
 *
 * <p>HTTP 侧配套（application.yml）：spring.jackson.deserialization.
 * fail-on-unknown-properties=true —— 未知业务写字段拒绝（DD 3.1 建议），
 * 绑定失败经 advice 转 400 INVALID_INPUT。</p>
 */
@Configuration
@EnableConfigurationProperties(AppProperties.class)
public class FoundationConfig {

    /** Jackson：解析入站 JSON 时拒绝重复对象键（STRICT_DUPLICATE_DETECTION）。 */
    @Bean
    public Jackson2ObjectMapperBuilderCustomizer strictDuplicateKeys() {
        return builder -> builder.featuresToEnable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
    }

    @Bean
    public TransactionTemplate transactionTemplate(PlatformTransactionManager txManager) {
        return new TransactionTemplate(txManager);
    }

    @Bean
    public WebMvcConfigurer principalContextWebConfigurer(PrincipalContextArgumentResolver resolver) {
        return new WebMvcConfigurer() {
            @Override
            public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
                resolvers.add(resolver);
            }
        };
    }

    @Bean
    @ConditionalOnMissingBean(MediaAccessPolicy.class)
    public MediaAccessPolicy devMediaAccessPolicy() {
        return new AllowAuthenticatedMediaAccessPolicy();
    }
}

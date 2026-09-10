package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
/**
 * dev 默认：任意已认证主体可读（替身媒体无真实用户数据）。
 * TODO(B/C/D)：生产必须替换为 purpose+业务归属授权（见接口注释）；
 * FoundationConfig 以 @Bean @ConditionalOnMissingBean 注册，业务包提供实现后自动失效。
 */
public class AllowAuthenticatedMediaAccessPolicy implements MediaAccessPolicy {

    @Override
    public boolean canAccess(PrincipalContext principal, MediaObject media) {
        return principal != null;
    }
}

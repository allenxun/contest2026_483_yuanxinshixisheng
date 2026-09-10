package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

/**
 * <b>dev 显式 opt-in</b>（app.media.allow-any-authenticated=true）：任意已认证
 * 主体可读，仅面向跨模块本地联调替身媒体（无真实用户数据）。
 * app.env=production 时该开关在 bean 装配点被拒绝（FoundationConfig 启动
 * 失败，fail closed）。默认实现是 {@link OwnerBasedMediaAccessPolicy}；
 * 业务授权（T05 报告引用/T02 关系/T03 当前任务）由 B/C/D @Primary 覆盖。
 */
public class AllowAuthenticatedMediaAccessPolicy implements MediaAccessPolicy {

    @Override
    public boolean canAccess(PrincipalContext principal, MediaObject media) {
        return principal != null;
    }
}

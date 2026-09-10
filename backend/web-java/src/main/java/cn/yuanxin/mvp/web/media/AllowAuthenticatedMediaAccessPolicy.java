package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

/**
 * <b>dev 显式 opt-in</b>（{@code app.media.access-mode=any-authenticated} 或
 * {@code app.media.allow-any-authenticated=true}）：任意已认证主体可读，仅面向
 * 跨模块本地联调替身媒体（无真实用户数据）。app.env=production 时该开关由
 * {@code ProductionFailClosedValidator} 无条件拒绝启动（与 bean 装配无关）。
 * 生产安全默认是 {@link DenyAllMediaAccessPolicy}；dev/test 上传者便利用
 * {@link OwnerBasedMediaAccessPolicy}（access-mode=owner-dev）；业务授权
 * （T05 报告引用/T02 关系/T03 当前任务）由 B/C/D @Primary 覆盖。
 */
public class AllowAuthenticatedMediaAccessPolicy implements MediaAccessPolicy {

    @Override
    public boolean canAccess(PrincipalContext principal, MediaObject media) {
        return principal != null;
    }
}

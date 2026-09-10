package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

/**
 * 逐次受控读取授权（DD 10.2：available ≠ 可访问）。
 *
 * <p>A 包生产安全默认是 {@link DenyAllMediaAccessPolicy}（一律拒绝，统一
 * 404）；dev/test 上传者便利是 {@link OwnerBasedMediaAccessPolicy}
 * （access-mode=owner-dev，核验用途仍拒绝）；任意已认证可读是显式 dev opt-in
 * {@link AllowAuthenticatedMediaAccessPolicy}。production 下任何非默认模式
 * 被 ProductionFailClosedValidator 拒绝启动。B/C/D 接线点：按 purpose + 业务
 * 归属（T05 冻结报告引用、T02 有效关系、T03 当前任务）提供 @Primary 实现
 * 替换默认。</p>
 */
public interface MediaAccessPolicy {

    /**
     * false → 与"资源不存在"<b>完全一致</b>的 404 RESOURCE_NOT_VISIBLE
     * （绝不 403——状态差异会泄露存在性/归属）。
     */
    boolean canAccess(PrincipalContext principal, MediaObject media);
}

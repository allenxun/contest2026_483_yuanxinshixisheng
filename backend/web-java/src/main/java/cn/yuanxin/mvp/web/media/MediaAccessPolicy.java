package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

/**
 * 逐次受控读取授权（DD 10.2：available ≠ 可访问）。
 *
 * <p>A 包默认实现 {@link OwnerBasedMediaAccessPolicy}（仅上传者本人）；
 * dev 联调可用 app.media.allow-any-authenticated=true 显式切换到
 * {@link AllowAuthenticatedMediaAccessPolicy}（production 下该开关被拒绝）。
 * B/C/D 接线点：按 purpose + 业务归属（T05 冻结报告引用、T02 有效关系、
 * T03 当前任务）提供 @Primary 实现替换默认。</p>
 */
public interface MediaAccessPolicy {

    /**
     * false → 与"资源不存在"<b>完全一致</b>的 404 RESOURCE_NOT_VISIBLE
     * （绝不 403——状态差异会泄露存在性/归属）。
     */
    boolean canAccess(PrincipalContext principal, MediaObject media);
}

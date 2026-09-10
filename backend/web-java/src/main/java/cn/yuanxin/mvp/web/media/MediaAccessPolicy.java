package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

/**
 * 逐次受控读取授权（DD 10.2：available ≠ 可访问）。
 *
 * <p>A 包默认实现 {@link AllowAuthenticatedMediaAccessPolicy} 仅面向 dev 替身；
 * B/C/D 接线点（TODO hook）：按 purpose + 业务归属（T05 冻结报告引用、
 * T02 有效关系、T03 当前任务）替换本接口的 @Primary 实现。</p>
 */
public interface MediaAccessPolicy {

    /** false → 403 CALLER_NOT_ALLOWED；资源不存在/未 available → 404 RESOURCE_NOT_VISIBLE。 */
    boolean canAccess(PrincipalContext principal, MediaObject media);
}

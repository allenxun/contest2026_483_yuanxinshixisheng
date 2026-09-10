package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

/**
 * A 包生产安全默认媒体授权：<b>一律拒绝</b>（oracle round-2 R2-1）。
 *
 * <p>任何媒体 GET 统一 404 RESOURCE_NOT_VISIBLE，不泄露存在性；直到 B/C/D
 * 按 DD 10.2 安装业务 {@code @Primary MediaAccessPolicy}（T05 冻结报告引用 /
 * T02 有效关系 / T03 当前任务）。owner-dev 便利仅 dev/test 显式开启。</p>
 */
public class DenyAllMediaAccessPolicy implements MediaAccessPolicy {

    @Override
    public boolean canAccess(PrincipalContext principal, MediaObject media) {
        return false;
    }
}

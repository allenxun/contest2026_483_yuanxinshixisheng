package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

import java.util.Locale;

/**
 * A 包默认媒体授权：<b>仅上传者本人可读</b>（owner-based DENY 其余）。
 *
 * <p>依据 DD 10.2 第 1 条"认证主体；T11 读取对象状态、用途和<b>归属</b>"：
 * 归属列由受理方写入（{@code uploader_type} = 主体类型小写，
 * {@code uploader_ref} = T13 规范主体文本 {@code <account_uuid>:<installation_id>}
 * 或 {@code <gimbal_uuid>}）。同账号不同安装也不可互读——installation 是
 * 上传主体身份的一部分（会话/目标按安装失效）。</p>
 *
 * <p>被拒/不存在统一 404 RESOURCE_NOT_VISIBLE（控制器裁决，绝不 403——
 * 不泄露资源存在性）。业务授权读（T05 冻结报告引用 / T02 有效关系 /
 * T03 当前任务，DD 10.2 第 2—3 条）是 B/C/D 的接线点：提供 @Primary
 * MediaAccessPolicy 实现替换本默认。真实凭据下本默认即最小可用面。</p>
 */
public class OwnerBasedMediaAccessPolicy implements MediaAccessPolicy {

    @Override
    public boolean canAccess(PrincipalContext principal, MediaObject media) {
        if (principal == null || media == null || media.uploaderType() == null
                || media.uploaderRef() == null) {
            return false;
        }
        String type = principal.principalType().name().toLowerCase(Locale.ROOT);
        return type.equals(media.uploaderType())
                && principal.t13PrincipalId().equals(media.uploaderRef());
    }
}

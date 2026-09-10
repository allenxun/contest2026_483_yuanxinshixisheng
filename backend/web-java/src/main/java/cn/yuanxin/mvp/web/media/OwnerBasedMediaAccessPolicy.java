package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;

import java.util.EnumSet;
import java.util.Locale;
import java.util.Set;

/**
 * <b>dev/test 显式便利</b>（{@code app.media.access-mode=owner-dev}）：仅上传者
 * 本人可读，且<b>核验用途一律拒绝</b>（grant_face / execution_face /
 * revalidation_face——即使对上传者也不放行，保留给 B/C/D 业务策略）。
 * app.env=production 下该模式被 ProductionFailClosedValidator 拒绝启动。
 *
 * <p>归属列为 {@code uploader_type}（主体类型小写 app/gimbal）+
 * {@code uploader_ref}（T13 规范主体文本 {@code <account_uuid>:<installation_id>}
 * 或 {@code <gimbal_uuid>}）。同账号不同安装也不可互读——installation 是
 * 上传主体身份的一部分（会话/目标按安装失效）。</p>
 *
 * <p>被拒/不存在统一 404 RESOURCE_NOT_VISIBLE（控制器裁决，绝不 403——
 * 不泄露资源存在性）。生产默认是 {@link DenyAllMediaAccessPolicy}；业务授权读
 * （T05 冻结报告引用 / T02 有效关系 / T03 当前任务，DD 10.2 第 2—3 条）是
 * B/C/D 的接线点：提供 @Primary MediaAccessPolicy 实现替换默认。</p>
 */
public class OwnerBasedMediaAccessPolicy implements MediaAccessPolicy {

    /** 人脸/核验用途：A 便利策略永不放行（保留给业务策略）。 */
    private static final Set<MediaPurpose> FACE_PURPOSES = EnumSet.of(
            MediaPurpose.GRANT_FACE,
            MediaPurpose.EXECUTION_FACE,
            MediaPurpose.REVALIDATION_FACE);

    @Override
    public boolean canAccess(PrincipalContext principal, MediaObject media) {
        if (principal == null || media == null || media.uploaderType() == null
                || media.uploaderRef() == null) {
            return false;
        }
        if (media.purpose() != null && FACE_PURPOSES.contains(media.purpose())) {
            return false;
        }
        String type = principal.principalType().name().toLowerCase(Locale.ROOT);
        return type.equals(media.uploaderType())
                && principal.t13PrincipalId().equals(media.uploaderRef());
    }
}

package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.media.MediaIntakeService;

import java.util.Optional;

/**
 * 人脸身份解析的 dev/test 替身（仅 dev/test profile；见
 * {@link FaceIdentityResolver} 的替身边界说明）。
 *
 * <p>确定性规则：{@code face_subject_ref = SHA-256(采集图片原始字节) 小写 hex}。
 * 真实提供方应按其自身人脸库返回 subject ref；本替身仅用于隔离测试与联调
 * （测试可用 {@link #subjectRefFor(byte[])} 预置相同引用），<b>不得用于生产</b>。</p>
 */
public class DevTestFaceIdentityResolver implements FaceIdentityResolver {

    private final String namespace;

    public DevTestFaceIdentityResolver(String namespace) {
        this.namespace = namespace;
    }

    @Override
    public String identityNamespace() {
        return namespace;
    }

    @Override
    public Optional<ResolvedFaceIdentity> resolve(byte[] content, FaceClassification classification) {
        if (classification != FaceClassification.MATCHED) {
            // 不确定/新人员/质量不合格/依赖失败都不构成可靠身份（fail closed）。
            return Optional.empty();
        }
        return Optional.of(new ResolvedFaceIdentity(namespace, subjectRefFor(content)));
    }

    /** 替身派生规则（测试预置 member 时使用同一规则）。 */
    public static String subjectRefFor(byte[] content) {
        return MediaIntakeService.sha256Hex(content);
    }
}

package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.identity.FaceIdentityResolver;
import cn.yuanxin.mvp.web.identity.ResolvedFaceIdentity;

import java.util.Optional;

/**
 * {@code app.face.provider=insightface} 下的<b>显式"身份解析未接入"</b>实现（红线 2）。
 *
 * <p>已部署的 InsightFace 服务<b>刻意不提供全库识别</b>（无 {@code /v1/recognize}），
 * 因此无法由一张脸反查出成员。dev/test 的 {@code DevTestFaceIdentityResolver} 用图片
 * 字节 SHA-256 冒充 {@code face_subject_ref}，<b>无任何真实身份语义</b>，绝不能在
 * insightface 模式下继续生效。本实现恒返回 {@link Optional#empty()}，使
 * {@code MemberAccessGrantService} 走既有 403 {@code FACE_NOT_VERIFIED}（同一非揭示消息）
 * ——应用可启动，但 M1-A01 <b>诚实拒绝</b>，绝不伪造身份、绝不用 sha256 冒充。</p>
 */
public class UnavailableFaceIdentityResolver implements FaceIdentityResolver {

    private final String namespace;

    public UnavailableFaceIdentityResolver(String namespace) {
        this.namespace = namespace;
    }

    @Override
    public String identityNamespace() {
        return namespace;
    }

    @Override
    public Optional<ResolvedFaceIdentity> resolve(byte[] content, FaceClassification classification) {
        return Optional.empty();
    }
}

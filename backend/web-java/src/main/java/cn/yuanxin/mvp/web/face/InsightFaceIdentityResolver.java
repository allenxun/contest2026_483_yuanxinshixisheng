package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.identity.FaceIdentityResolver;
import cn.yuanxin.mvp.web.identity.ResolvedFaceIdentity;

import java.util.Optional;

/**
 * {@code app.face.provider=insightface} 下的身份解析实现：用 namespace 限定的只读 1:N 搜索
 * 把一次人脸核验映射为成员身份引用 {@code (identityNamespace, face_subject_ref)}。
 *
 * <p><b>保守性</b>：仅当输入分类为 {@link FaceClassification#MATCHED} 时才调用远端搜索；
 * 其余分类（不确定/质量不合格/依赖失败/新人员）一律直接 {@link Optional#empty()}，
 * 不产生任何远端调用。搜索未命中或不确定同样返回 empty。绝不猜测身份、绝不用 sha256 冒充。</p>
 *
 * <p><b>两次搜索是刻意取舍（必须如实披露）</b>：A 域接口
 * {@code auth/FaceProvider.classify(purpose, content)} <b>无法携带 {@code subjectRef}</b>，
 * 而 {@code MemberAccessGrantService} 的 {@code MATCHED} 门与
 * {@code resolve(content, classification)} 签名都<b>不能改</b>（改门会破坏 doubles 语义与 E 的
 * 既有"UNCERTAIN → 403"场景）。因此 insightface 模式下 M1-A01 会有<b>两次推理调用</b>：
 * {@code classify} 一次 + {@code resolve} 一次。第二次搜索若与第一次不一致（库在此期间变化）
 * ⇒ 返回 empty ⇒ 403，这是<b>保守正确</b>的行为。
 * <b>单调用优化需要改 A 域 {@code FaceProvider} 接口</b>（让它能返回身份引用），属跨包协调项，
 * 见 {@code backend/handoffs/B-face-java.md}。</p>
 *
 * <p><b>未完成声明</b>：即便本解析器能解析出 {@code subject_ref}，只要
 * {@code members.face_subject_ref} 无人填充（当前唯一生产写入方是 D 包 Python），
 * 只读成员定位仍查不到行 ⇒ M1-A01 恒 403 {@code FACE_NOT_VERIFIED}。
 * 这是<b>诚实拒绝，不是伪造成功</b>。</p>
 */
public class InsightFaceIdentityResolver implements FaceIdentityResolver {

    private final FaceIdentityPort port;
    private final String namespace;

    public InsightFaceIdentityResolver(FaceIdentityPort port, InsightFaceProperties properties) {
        this.port = port;
        this.namespace = properties.namespace();
    }

    @Override
    public String identityNamespace() {
        return namespace;
    }

    @Override
    public Optional<ResolvedFaceIdentity> resolve(byte[] content, FaceClassification classification) {
        if (classification != FaceClassification.MATCHED) {
            // 保守：没有 MATCHED 分类就没有第二次搜索，更不会猜测身份。
            return Optional.empty();
        }
        FaceSearchResult result = port.search("grant", content);
        if (!result.matched()) {
            // 第一次分类与第二次搜索不一致（库变化/歧义）：拒绝，绝不降级放行。
            return Optional.empty();
        }
        return Optional.of(new ResolvedFaceIdentity(identityNamespace(), result.subjectRef()));
    }
}
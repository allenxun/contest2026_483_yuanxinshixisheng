package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;

import java.util.Set;

/**
 * InsightFace {@link FaceProvider} 适配器（{@code app.face.provider=insightface}）。
 *
 * <p><b>修订后的红线①（逐字，2026-09-16 冻结）</b>：{@link #classify} <b>永不</b>返回
 * {@link FaceClassification#RELIABLE_NEW}——"未命中"不是"可靠新人"的证据
 * （依据 {@code backend/doc/后端详细设计-V1-MVP.md:657,663}）；{@link FaceClassification#MATCHED}
 * <b>只能</b>来自 namespace 限定的 1:N 搜索命中（携带 {@code subjectRef}），<b>绝不</b>来自仅
 * {@code /v1/extract}。旧红线"永不 MATCHED"的前提是"只有 extract、无成员语义"，该前提已被 1:N 搜索
 * 改变；{@code MATCHED} 本身<b>不</b>授予任何权限——{@code MemberAccessGrantService} 仍要求
 * {@code resolve} 得到 {@code subject_ref} <b>且</b>只读定位到 {@code status='active'} 的成员行，
 * 否则 403 {@code FACE_NOT_VERIFIED}。</p>
 *
 * <p><b>映射</b>：{@code port.search("grant", content)} 结果
 * {@link FaceSearchDecision#MATCHED} ⇒ {@link FaceClassification#MATCHED}；
 * {@code no_match}/{@code uncertain} ⇒ {@link FaceClassification#UNCERTAIN}；
 * {@code NO_FACE}/{@code MULTI_FACES_AMBIGUOUS}/{@code IMAGE_DECODE_FAILED}/
 * {@code QUALITY_INSUFFICIENT} ⇒ {@link FaceClassification#QUALITY_REJECTED}；
 * 其余（依赖/配置/网络/形状异常）⇒ {@link FaceClassification#DEPENDENCY_FAILED}。</p>
 */
public class InsightFaceProvider implements FaceProvider {

    /** 图像质量类服务码（映射 QUALITY_REJECTED，先于一般分类）。 */
    static final Set<String> QUALITY_CODES = Set.of(
            "NO_FACE",
            "MULTI_FACES_AMBIGUOUS",
            "IMAGE_DECODE_FAILED",
            "QUALITY_INSUFFICIENT");

    private final FaceIdentityPort port;

    public InsightFaceProvider(FaceIdentityPort port) {
        this.port = port;
    }

    @Override
    public FaceClassification classify(String purpose, byte[] content) {
        try {
            FaceSearchResult result = port.search(purpose, content);
            // 只有 namespace 限定的 1:N 命中才是 MATCHED；未命中的库状态不得当作"可靠新人"。
            return result.decision() == FaceSearchDecision.MATCHED
                    ? FaceClassification.MATCHED
                    : FaceClassification.UNCERTAIN;
        } catch (FaceServiceException failure) {
            if (QUALITY_CODES.contains(failure.error().safeCode())) {
                return FaceClassification.QUALITY_REJECTED;
            }
            return FaceClassification.DEPENDENCY_FAILED;
        } catch (RuntimeException unexpected) {
            return FaceClassification.DEPENDENCY_FAILED;
        }
    }
}
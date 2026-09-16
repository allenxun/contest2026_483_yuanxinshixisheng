package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;

import java.util.Set;

/**
 * InsightFace {@link FaceProvider} 适配器（{@code app.face.provider=insightface}）。
 *
 * <p><b>核心取舍（红线 1）</b>：{@link FaceProvider#classify(String, byte[])} <b>没有成员参数</b>，
 * 无法证明"当前人脸 = 指定成员"（总协调 2026-09-11 裁定，见 {@code CareFaceVerifier} javadoc）。
 * 因此本实现<b>永不</b>返回 {@link FaceClassification#MATCHED}、<b>永不</b>返回
 * {@link FaceClassification#RELIABLE_NEW}（新服务刻意不提供全库检索，未匹配 ≠ 可靠新人；
 * 见 {@code backend/handoffs/B-face-integration-gaps.md} G1/G2/G3）。</p>
 *
 * <p>映射：{@code /v1/extract} 成功检出人脸 → {@link FaceClassification#UNCERTAIN}；
 * {@code NO_FACE}/{@code MULTI_FACES_AMBIGUOUS}/{@code IMAGE_DECODE_FAILED}/
 * {@code QUALITY_INSUFFICIENT} → {@link FaceClassification#QUALITY_REJECTED}；
 * 其余（含依赖故障与配置错误）→ {@link FaceClassification#DEPENDENCY_FAILED}。
 * 真实 1:1 由 {@link InsightFaceCareVerifier} 承担。</p>
 */
public class InsightFaceProvider implements FaceProvider {

    /** 图像质量类服务码（映射 QUALITY_REJECTED，先于一般分类）。 */
    static final Set<String> QUALITY_CODES = Set.of(
            "NO_FACE",
            "MULTI_FACES_AMBIGUOUS",
            "IMAGE_DECODE_FAILED",
            "QUALITY_INSUFFICIENT");

    private final FaceServiceClient client;

    public InsightFaceProvider(FaceServiceClient client) {
        this.client = client;
    }

    @Override
    public FaceClassification classify(String purpose, byte[] content) {
        try {
            client.extract(content);
            // 成功检出人脸 ≠ 匹配某个成员：无成员参数，只能是 UNCERTAIN。
            return FaceClassification.UNCERTAIN;
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

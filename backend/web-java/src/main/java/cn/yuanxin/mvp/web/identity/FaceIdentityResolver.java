package cn.yuanxin.mvp.web.identity;

import cn.yuanxin.mvp.web.auth.FaceClassification;

import java.util.Optional;

/**
 * M1 人脸身份解析端口（服务端受控）。
 *
 * <p>负责把一次人脸核验的分类结果映射为可靠的成员身份引用
 * {@code (identity_namespace, face_subject_ref)}。身份命名空间由服务端配置
 * 提供（{@code app.identity.namespace}），<b>绝不接受客户端传入</b>；
 * face_subject_ref 由提供方/服务端派生。</p>
 *
 * <p>真实人脸供应商尚未选定，A 的 {@code FaceProvider} 端口只返回分类枚举，
 * 不含身份引用。因此当前实现是<b>明确命名的 dev/test 替身</b>
 * （{@link DevTestFaceIdentityResolver}）：仅 {@code MATCHED} 时按图片内容
 * 的 SHA-256 派生确定性的 subject ref，供隔离测试/联调；生产 profile 无该
 * bean → 注入失败即启动失败（fail closed）。</p>
 */
public interface FaceIdentityResolver {

    /** 服务端受控的身份命名空间。 */
    String identityNamespace();

    /**
     * 按分类与采集内容解析身份引用。
     *
     * @return 仅可靠匹配（{@link FaceClassification#MATCHED}）时返回身份；
     *         其余分类（不确定/质量不合格/依赖失败/新人员）一律 empty。
     */
    Optional<ResolvedFaceIdentity> resolve(byte[] content, FaceClassification classification);
}

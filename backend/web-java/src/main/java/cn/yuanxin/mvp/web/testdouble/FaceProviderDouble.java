package cn.yuanxin.mvp.web.testdouble;

import cn.yuanxin.mvp.web.auth.FaceClassification;
import cn.yuanxin.mvp.web.auth.FaceProvider;

/**
 * 人脸提供方测试替身（仅 dev/test）：返回配置的固定分类
 * （app.testdouble.face.classification，默认 MATCHED；测试可 setClassification）。
 * 真实供应商（阿里云 PoC/腾讯云对照）未选定——A 只交付端口+替身。
 */
public class FaceProviderDouble implements FaceProvider {

    private volatile FaceClassification configured;

    public FaceProviderDouble(String classification) {
        this.configured = FaceClassification.valueOf(
                classification == null ? "MATCHED" : classification.toUpperCase());
    }

    @Override
    public FaceClassification classify(String purpose, byte[] content) {
        return configured;
    }

    /** 测试钩子：按用例切换分类（含 QUALITY_REJECTED/DEPENDENCY_FAILED）。 */
    public void setClassification(FaceClassification c) {
        this.configured = c;
    }
}

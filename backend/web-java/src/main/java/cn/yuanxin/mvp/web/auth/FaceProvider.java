package cn.yuanxin.mvp.web.auth;

/**
 * 人脸提供方适配端口（digest §6：Java 请求内同步调用，不排队列）。
 * A 包仅端口 + 替身；真实供应商（阿里云 PoC/腾讯云对照）未选定。
 */
public interface FaceProvider {

    /**
     * 对受控媒体内容做同步分类。
     *
     * @param purpose 采集用途（grant/admission/revalidation/assessment 文本）
     * @param content 图片原始字节（调用方已从 StoragePort 读出）
     */
    FaceClassification classify(String purpose, byte[] content);
}

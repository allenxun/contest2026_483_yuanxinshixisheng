package cn.yuanxin.mvp.web.face;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 阿里云人脸 provider 的<b>配置边界</b>（{@code app.face.aliyun.*}）——<b>仅键名与类型</b>，
 * 不含任何实现。{@code app.face.provider=aliyun} 会在启动期被
 * {@link AliyunFaceBoundaryConfig} 明确拒绝（未实现），绝不静默回退 doubles、绝不臆造能力。
 *
 * <p>字段仅用于表达将要接入的配置面；{@link #toString()} 脱敏。</p>
 */
@ConfigurationProperties(prefix = "app.face.aliyun")
public record AliyunFaceProperties(
        String region,
        String endpoint,
        String accessKeyId,
        String accessKeySecret,
        String securityToken,
        String serviceName) {

    @Override
    public String toString() {
        return "AliyunFaceProperties[region=" + region + ", endpoint=" + endpoint
                + ", accessKeyId=" + redacted(accessKeyId)
                + ", accessKeySecret=" + redacted(accessKeySecret)
                + ", securityToken=" + redacted(securityToken)
                + ", serviceName=" + serviceName + "]";
    }

    private static String redacted(String value) {
        return value == null ? "<absent>" : "<redacted>";
    }
}

package cn.yuanxin.mvp.web.storage;

import com.aliyun.oss.OSS;

import java.net.URL;
import java.time.Duration;
import java.util.Date;
import java.util.Objects;

/**
 * 公网签名地址生成器：用**独立**的、由 {@code app.storage.oss.public-endpoint} 构建的
 * {@link OSS} 客户端调用 SDK {@code generatePresignedUrl}。
 *
 * <p><b>按最终访问域名直接签名（工程正确性约束）</b>：签名必须在针对公网 endpoint 构建的
 * 客户端上完成；本类<b>不</b>对已签名 URL 做任何 host/scheme 字符串替换，也<b>不</b>使用
 * {@code ossClient.setEndpoint(...)} 在共享客户端上动态切换 endpoint（那会影响并发的对象操作，
 * 且 SDK 没有"同一 client 对象操作走 A endpoint、签名走 B endpoint"的通用参数）。
 * 说明：V1 签名字符串（{@code VERB/CONTENT-MD5/CONTENT-TYPE/EXPIRES/CanonicalizedOSSHeaders/
 * CanonicalizedResource}）<b>不含 Host</b>，因此替换 host 在 V1 下技术上常仍能通过验证；
 * 但 V4 把 {@code host} 列入额外签名头、region 恒参与 Credential Scope，且 CNAME/传输加速
 * 路由与 SDK 版本默认行为都可能变化 ⇒ 依赖"签名后改 host"<b>不可靠</b>。这是工程正确性约束，
 * 不是"V1 算法必然失败"。</p>
 *
 * <p><b>签名版本</b>：当前<b>沿用 SDK 默认的 V1</b>（未调用
 * {@code ClientBuilderConfiguration.setSignatureVersion}）。两个客户端都设置 {@code region}。</p>
 *
 * <p><b>自定义域名</b>：<b>未</b>启用 {@code setSupportCname(true)}；{@code public-endpoint}
 * 目前按标准 OSS 域名处理（CNAME 场景需另行评估）。</p>
 *
 * <p><b>有效期与 STS</b>：默认 15 分钟。预签名 URL 的最大有效期为 <b>7 天（604800 秒）</b>
 * （V4 硬上限，本实现作为保守上限），超过则<b>明确失败</b>（不静默截断）。若使用 STS 临时凭据，
 * URL 的实际有效期 = {@code min(URL TTL, STS token 剩余有效期)}；token 过期后 URL 立即失效。</p>
 *
 * <p><b>风险与暴露面</b>：预签名 URL 是"持有即可用"的临时授权，在有效期内会把对应对象暴露在
 * 互联网上。本轮<b>不接入任何 HTTP 面</b>：是否对 APP/云台暴露签名地址属架构决定，由根裁定。</p>
 *
 * <p>生命周期：本类不拥有客户端；两个客户端均由 Spring 装配管理并各自 {@code shutdown()}。</p>
 */
public class OssPublicUrlSigner {

    /** 默认有效期（15 分钟）。 */
    public static final Duration DEFAULT_EXPIRY = Duration.ofMinutes(15);

    /**
     * 预签名 URL 最小有效期（1 秒）。**下界不是形式要求**：SDK 侧用
     * {@code new Date(currentTimeMillis + ttl.toMillis())} 计算过期时刻，任何小于 1 秒的正
     * {@link Duration} 都会因毫秒截断变成 0 ⇒ 生成**立即过期**的 URL（看似成功、实际不可用）。
     * 取 1 秒亦与 Python 侧 {@code sign_public_url} 的整数秒 {@code 1..604800} 校验一致。
     */
    public static final Duration MIN_EXPIRY = Duration.ofSeconds(1);

    /** 预签名 URL 最大有效期（7 天 = 604800 秒）：超过即明确失败。 */
    public static final Duration MAX_EXPIRY = Duration.ofDays(7);

    private final OSS publicClient;
    private final String bucket;

    public OssPublicUrlSigner(OSS publicClient, String bucket) {
        this.publicClient = Objects.requireNonNull(publicClient, "publicClient");
        this.bucket = Objects.requireNonNull(bucket, "bucket");
    }

    /** 用默认有效期生成指定对象的公网签名地址。 */
    public URL presign(String objectKey) {
        return presign(objectKey, DEFAULT_EXPIRY);
    }

    /**
     * 用给定有效期生成签名地址。TTL 为 null 或落在 {@code [MIN_EXPIRY, MAX_EXPIRY]} 之外
     * ⇒ <b>明确失败</b>（{@link IllegalArgumentException}），<b>绝不</b>静默回退到
     * {@link #DEFAULT_EXPIRY}、也<b>绝不</b>静默截断：有效期是安全相关参数，静默替换会让调用方
     * 误以为拿到了自己请求的授权时长。需要默认值请显式调用 {@link #presign(String)}。
     *
     * <p>下界 {@link #MIN_EXPIRY}（1 秒）尤其重要：{@code Duration.ofNanos(1).toMillis() == 0}，
     * 若只拒绝 null/零/负数，亚秒级 TTL 会生成**立即过期**的 URL。</p>
     */
    public URL presign(String objectKey, Duration expiry) {
        Objects.requireNonNull(objectKey, "objectKey");
        if (expiry == null || expiry.compareTo(MIN_EXPIRY) < 0) {
            throw new IllegalArgumentException("presign expiry must be a positive duration of at least "
                    + MIN_EXPIRY.toSeconds() + " second(s) (call presign(objectKey) for the explicit default of "
                    + DEFAULT_EXPIRY.toSeconds() + " seconds)");
        }
        Duration ttl = expiry;
        if (ttl.compareTo(MAX_EXPIRY) > 0) {
            throw new IllegalArgumentException("requested presign ttl exceeds the maximum of "
                    + MAX_EXPIRY.toSeconds() + " seconds");
        }
        Date expiration = new Date(System.currentTimeMillis() + ttl.toMillis());
        // 直接用公网客户端签名；返回 URL 原样透传，不做 host/scheme 替换或其它后处理。
        return publicClient.generatePresignedUrl(bucket, objectKey, expiration);
    }

    /** 生成签名地址并返回其 host（仅用于探测/断言，不暴露完整 URL）。 */
    public String presignedHost(String objectKey) {
        return presign(objectKey).getHost();
    }
}

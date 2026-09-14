package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import com.aliyun.oss.OSS;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * B 真实 OSS 跨语言 smoke 的 Java 侧 CLI 入口（root-only）。由驱动以
 * {@code java -cp target/test-classes:target/classes:<deps> cn.yuanxin.mvp.web.storage.OssLiveSmokeRunner ...}
 * 调用；类名不以 {@code Test}/{@code IT} 结尾 ⇒ surefire 绝不执行它。
 *
 * <p>仅做接线：真实 OSS 只经生产装配 {@link OssProvidersConfig#ossClient} 构造，put/get/exists/delete
 * 全部由 {@link OssStorageAdapter} 执行；{@code --mode double} 用 {@link FileSystemStorageDouble}。
 * 安全与格式逻辑在 {@link OssLiveSmoke}（可单测）。</p>
 */
public final class OssLiveSmokeRunner {

    private OssLiveSmokeRunner() {
    }

    public static void main(String[] rawArgs) {
        boolean liveOptIn = Boolean.getBoolean("app.oss.live-smoke");
        int exitCode = OssLiveSmoke.run(rawArgs, System.out, liveOptIn,
                OssLiveSmokeRunner::httpProbe, OssLiveSmokeRunner::openStorage);
        System.out.flush();
        System.exit(exitCode);
    }

    /** live ⇒ 生产装配 + 生产适配器；double ⇒ 文件系统替身。 */
    static OssLiveSmoke.StorageSession openStorage(String mode, OssLiveSmoke.Args args,
                                                   OssLiveSmoke.LiveConfig config) {
        if ("double".equals(mode)) {
            FileSystemStorageDouble storage = new FileSystemStorageDouble(args.doubleRoot());
            return session(storage, () -> {
            });
        }
        // 与 OssProvidersConfig:59-71 完全一致的参数：endpoint/region/credentials/超时。
        AliyunOssProperties properties = new AliyunOssProperties(
                config.region(), config.endpoint(), config.bucket(),
                config.accessKeyId(), config.accessKeySecret(), config.securityToken(), null, null);
        // 生产装配要求 app.storage.bucket 与 app.storage.oss.bucket 一致。
        AppProperties appProperties = new AppProperties(null, null,
                new AppProperties.Storage(null, config.bucket()), null, null, null, null);
        OSS oss = new OssProvidersConfig().ossClient(properties, appProperties);
        OssStorageAdapter adapter = new OssStorageAdapter(oss, properties.bucket());
        return session(adapter, oss::shutdown);
    }

    private static OssLiveSmoke.StorageSession session(StoragePort port, Runnable close) {
        return new OssLiveSmoke.StorageSession() {
            @Override
            public StoragePort port() {
                return port;
            }

            @Override
            public void close() {
                close.run();
            }
        };
    }

    /** 未鉴权 GET（无 Authorization、不跟随重定向、10s 超时）；只返回状态码，绝不打印 URL。 */
    static int httpProbe(String endpoint, String bucket, String objectKey) throws Exception {
        URI uri = OssLiveSmoke.publicUrl(endpoint, bucket, objectKey);
        HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .header("Accept", "*/*")
                .build();
        HttpResponse<Void> response = client.send(request, HttpResponse.BodyHandlers.discarding());
        return response.statusCode();
    }
}

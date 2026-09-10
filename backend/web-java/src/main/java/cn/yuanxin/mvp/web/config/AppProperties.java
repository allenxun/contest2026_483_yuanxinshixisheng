package cn.yuanxin.mvp.web.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 应用配置（前缀 app.*；全部 env 可覆盖，见 application.yml）：
 * env（对象 key 前缀/环境标记）、providers.mode（doubles|disabled|real）、
 * storage（dev 替身目录/桶名）、limits（单图上限 10MiB 开发初值）、
 * idempotency（T13 处理租约 30s）、media（dev 开放读 opt-in 开关）、
 * jobs（T12 默认 max_attempts，与 worker 重试配置对齐）。
 */
@ConfigurationProperties(prefix = "app")
public record AppProperties(String env, Providers providers, Storage storage,
                            Limits limits, Idempotency idempotency, Media media,
                            Jobs jobs) {

    public AppProperties {
        if (env == null || env.isBlank()) {
            env = "dev";
        }
        if (providers == null) {
            providers = new Providers(null);
        }
        if (storage == null) {
            storage = new Storage(null, null);
        }
        if (limits == null) {
            limits = new Limits(null);
        }
        if (idempotency == null) {
            idempotency = new Idempotency(null);
        }
        if (media == null) {
            media = new Media(false);
        }
        if (jobs == null) {
            jobs = new Jobs(null);
        }
    }

    public record Providers(String mode) {
        public String mode() {
            return mode == null || mode.isBlank() ? "doubles" : mode;
        }
    }

    public record Storage(String devDir, String bucket) {
        public String devDir() {
            return devDir == null || devDir.isBlank() ? "/tmp/mvp-a-storage" : devDir;
        }

        public String bucket() {
            return bucket == null || bucket.isBlank() ? "mvp-a-media" : bucket;
        }
    }

    public record Limits(Long imageMaxBytes) {
        public long maxImageBytes() {
            return imageMaxBytes == null ? 10_485_760L : imageMaxBytes;
        }
    }

    public record Idempotency(Integer leaseSeconds) {
        public int leaseSecondsOrDefault() {
            return leaseSeconds == null || leaseSeconds < 1 ? 30 : leaseSeconds;
        }
    }

    /**
     * media.allowAnyAuthenticated：dev 跨模块联调专用"任意已认证可读"开关，
     * 默认 false（owner-based 最小权限）；app.env=production 且开关为 true →
     * 启动失败（FoundationConfig fail closed）。
     */
    public record Media(boolean allowAnyAuthenticated) {
    }

    /** jobs.maxAttempts：JobEnqueuer 写 async_jobs.max_attempts 的默认（oracle M8）。 */
    public record Jobs(Integer maxAttempts) {
        public int maxAttemptsOrDefault() {
            return maxAttempts == null || maxAttempts < 1 ? 5 : maxAttempts;
        }
    }
}

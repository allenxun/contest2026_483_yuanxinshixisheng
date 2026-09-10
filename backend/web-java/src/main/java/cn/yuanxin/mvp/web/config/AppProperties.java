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
            media = new Media(false, null);
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

    /** 媒体授权模式（app.media.access-mode；仅 dev/test 生效）。 */
    public static final String MEDIA_MODE_DENY_ALL = "deny-all";
    public static final String MEDIA_MODE_OWNER_DEV = "owner-dev";
    public static final String MEDIA_MODE_ANY_AUTHENTICATED = "any-authenticated";

    /**
     * media.accessMode：默认 {@code deny-all}（生产安全默认，任何媒体 GET
     * 统一 404，直到 B/C/D 安装业务 @Primary MediaAccessPolicy）；
     * {@code owner-dev}=仅上传者本人可读的 dev/test 便利（核验用途仍拒绝）；
     * {@code any-authenticated}=显式 dev 联调开放。app.env=production 下任何
     * 非默认 access-mode 或 allowAnyAuthenticated=true →
     * ProductionFailClosedValidator 无条件拒绝启动（与 bean 装配无关）。
     */
    public record Media(boolean allowAnyAuthenticated, String accessMode) {
        public Media {
            if (accessMode == null || accessMode.isBlank()) {
                accessMode = MEDIA_MODE_DENY_ALL;
            }
        }

        public String accessModeOrDefault() {
            return accessMode;
        }

        public boolean defaultMode() {
            return MEDIA_MODE_DENY_ALL.equals(accessMode);
        }
    }

    /** jobs.maxAttempts：JobEnqueuer 写 async_jobs.max_attempts 的默认（oracle M8）。 */
    public record Jobs(Integer maxAttempts) {
        public int maxAttemptsOrDefault() {
            return maxAttempts == null || maxAttempts < 1 ? 5 : maxAttempts;
        }
    }
}

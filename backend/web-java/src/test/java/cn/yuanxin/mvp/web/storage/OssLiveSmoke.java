package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.media.StoragePort;
import org.yaml.snakeyaml.Yaml;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.io.Reader;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * B 真实 OSS 跨语言 smoke 的 Java 侧<b>纯逻辑 harness</b>（root-only、默认绝不执行）。
 *
 * <p>逐字实现 {@code .coordination/B-work/oss-live-smoke/contract.md}：对象键校验（§1）、
 * {@link #smokeBytes}（§2）、阶段执行（§3）、输出行格式化与净化（§4）、三重 opt-in（§5）、
 * UTF-8 YAML 配置读取（§6）。不持有 Spring 上下文；网络/真实 OSS 只发生在 live 模式且由
 * {@link OssLiveSmokeRunner} 注入。</p>
 *
 * <p><b>红线</b>：绝不 list/清空桶；delete 只删单个精确键；绝不输出 bucket/endpoint/region/
 * 完整 key/AK/SK/STS/对象内容；错误消息先经 {@link Redactor} 净化。</p>
 */
public final class OssLiveSmoke {

    public static final String SIDE = "java";
    public static final String PURPOSE = "assessment_result";
    public static final String CONTENT_TYPE = "application/octet-stream";
    public static final int DEFAULT_CONTENT_BYTES = 256;

    static final Pattern OBJECT_KEY_PATTERN = Pattern.compile(
            "^[a-z0-9][a-z0-9._-]{0,31}/assessment_result/"
                    + "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$");

    static final List<String> PHASES = List.of("write", "verify", "delete", "confirm-absent", "public-url-probe");
    static final List<String> MODES = List.of("live", "double");

    private OssLiveSmoke() {
    }

    // ---------------------------------------------------------------- §2

    /** 契约 §2 的跨语言合成内容算法（两侧逐字一致）。 */
    public static byte[] smokeBytes(String seed, int nbytes) {
        if (seed == null) {
            throw new IllegalArgumentException("content seed must not be null");
        }
        if (nbytes < 0) {
            throw new IllegalArgumentException("content bytes must be >= 0");
        }
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException unavailable) {
            throw new IllegalStateException("SHA-256 unavailable", unavailable);
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream(Math.max(32, nbytes));
        int i = 0;
        while (out.size() < nbytes) {
            digest.reset();
            digest.update((seed + ":" + i).getBytes(StandardCharsets.UTF_8));
            out.writeBytes(digest.digest());
            i++;
        }
        byte[] all = out.toByteArray();
        return all.length == nbytes ? all : Arrays.copyOf(all, nbytes);
    }

    public static byte[] sha256(byte[] content) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(content);
        } catch (NoSuchAlgorithmException unavailable) {
            throw new IllegalStateException("SHA-256 unavailable", unavailable);
        }
    }

    public static String sha256Hex(byte[] content) {
        return HexFormat.of().formatHex(sha256(content));
    }

    /** 契约 §4：{@code sha256} 字段取前 12 位十六进制。 */
    public static String sha256Hex12(byte[] content) {
        return sha256Hex(content).substring(0, 12);
    }

    /** 契约 §4：{@code keyDigest = sha256(objectKey UTF-8)} 前 12 位。 */
    public static String keyDigest(String objectKey) {
        return sha256Hex(objectKey.getBytes(StandardCharsets.UTF_8)).substring(0, 12);
    }

    // ---------------------------------------------------------------- §1

    /** 契约 §1 的对象键校验（正则 + 显式负例）。 */
    public static boolean isValidObjectKey(String objectKey) {
        if (objectKey == null || objectKey.isBlank()) {
            return false;
        }
        if (objectKey.contains("..")) {
            return false;
        }
        if (objectKey.startsWith("/") || objectKey.endsWith("/")) {
            return false;
        }
        String[] parts = objectKey.split("/", -1);
        if (parts.length != 3) {
            return false;
        }
        if (!PURPOSE.equals(parts[1])) {
            return false;
        }
        return OBJECT_KEY_PATTERN.matcher(objectKey).matches();
    }

    // ---------------------------------------------------------------- §3 args

    public record Args(String mode, String phase, String objectKey, String contentSeed,
                       int contentBytes, String doubleRoot, String configPath) {
    }

    public static Args parseArgs(String[] argv) {
        String mode = null;
        String phase = null;
        String objectKey = null;
        String seed = null;
        String doubleRoot = null;
        String config = null;
        int contentBytes = DEFAULT_CONTENT_BYTES;
        boolean contentBytesSet = false;
        for (int i = 0; i < argv.length; i++) {
            String flag = argv[i];
            switch (flag) {
                case "--mode" -> mode = requireValue(argv, ++i, flag);
                case "--phase" -> phase = requireValue(argv, ++i, flag);
                case "--object-key" -> objectKey = requireValue(argv, ++i, flag);
                case "--content-seed" -> seed = requireValue(argv, ++i, flag);
                case "--double-root" -> doubleRoot = requireValue(argv, ++i, flag);
                case "--config" -> config = requireValue(argv, ++i, flag);
                case "--content-bytes" -> {
                    String raw = requireValue(argv, ++i, flag);
                    try {
                        contentBytes = Integer.parseInt(raw);
                    } catch (NumberFormatException invalid) {
                        throw new IllegalArgumentException("--content-bytes must be an integer");
                    }
                    contentBytesSet = true;
                }
                default -> throw new IllegalArgumentException("unknown argument: " + flag);
            }
        }
        if (mode == null || !MODES.contains(mode)) {
            throw new IllegalArgumentException("--mode must be one of " + MODES);
        }
        if (phase == null || !PHASES.contains(phase)) {
            throw new IllegalArgumentException("--phase must be one of " + PHASES);
        }
        if (objectKey == null || objectKey.isBlank()) {
            throw new IllegalArgumentException("--object-key is required");
        }
        if (("write".equals(phase) || "verify".equals(phase)) && (seed == null || seed.isBlank())) {
            throw new IllegalArgumentException("--content-seed is required for phase " + phase);
        }
        if (contentBytesSet && contentBytes < 0) {
            throw new IllegalArgumentException("--content-bytes must be >= 0");
        }
        if ("double".equals(mode) && (doubleRoot == null || doubleRoot.isBlank())) {
            throw new IllegalArgumentException("--double-root is required for mode=double");
        }
        if ("live".equals(mode) && (config == null || config.isBlank())) {
            throw new IllegalArgumentException("--config is required for mode=live");
        }
        return new Args(mode, phase, objectKey, seed, contentBytes, doubleRoot, config);
    }

    private static String requireValue(String[] argv, int index, String flag) {
        if (index >= argv.length || argv[index].startsWith("--")) {
            throw new IllegalArgumentException(flag + " requires a value");
        }
        return argv[index];
    }

    // ---------------------------------------------------------------- §6 config

    /** 配置来源：与 {@code AliyunOssProperties} 组件一一对应（值绝不打印）。 */
    public record LiveConfig(String provider, String region, String endpoint, String bucket,
                             String accessKeyId, String accessKeySecret, String securityToken) {
    }

    /** 用 snakeyaml 读 UTF-8 YAML（严禁 ISO-8859-1）。同时兼容嵌套与点号扁平键。 */
    @SuppressWarnings("unchecked")
    public static LiveConfig loadYamlConfig(java.nio.file.Path path) throws IOException {
        try (Reader reader = new InputStreamReader(
                new FileInputStream(path.toFile()), StandardCharsets.UTF_8)) {
            Object loaded = new Yaml().load(reader);
            if (!(loaded instanceof Map<?, ?> root)) {
                throw new IllegalArgumentException("config root is not a YAML mapping");
            }
            Map<String, Object> map = (Map<String, Object>) root;
            return new LiveConfig(
                    value(map, "app.storage.provider"),
                    value(map, "app.storage.oss.region"),
                    value(map, "app.storage.oss.endpoint"),
                    value(map, "app.storage.oss.bucket"),
                    value(map, "app.storage.oss.access-key-id"),
                    value(map, "app.storage.oss.access-key-secret"),
                    value(map, "app.storage.oss.security-token"));
        }
    }

    private static String value(Map<String, Object> root, String dotted) {
        Object flat = root.get(dotted);
        if (flat != null) {
            return String.valueOf(flat).trim();
        }
        Object current = root;
        for (String part : dotted.split("\\.")) {
            if (!(current instanceof Map<?, ?> map)) {
                return null;
            }
            current = map.get(part);
        }
        return current == null ? null : String.valueOf(current).trim();
    }

    // ---------------------------------------------------------------- §5 gate

    public record Gate(boolean pass, String reason, String step, List<String> missingKeys) {
    }

    /** 三重 opt-in；任一不满足即 abort（绝不静默通过）。 */
    public static Gate evaluateGate(String mode, LiveConfig config, boolean liveOptIn) {
        if ("double".equals(mode)) {
            if (liveOptIn) {
                return new Gate(false, "not-opted-in", "double-mode-refuses-live-opt-in", List.of());
            }
            return new Gate(true, "none", "gate", List.of());
        }
        if (config == null || !"aliyun".equals(config.provider())) {
            return new Gate(false, "not-opted-in", "provider-not-aliyun", List.of());
        }
        List<String> missing = new ArrayList<>();
        if (isBlank(config.bucket())) {
            missing.add("app.storage.oss.bucket");
        }
        if (isBlank(config.accessKeyId())) {
            missing.add("app.storage.oss.access-key-id");
        }
        if (isBlank(config.accessKeySecret())) {
            missing.add("app.storage.oss.access-key-secret");
        }
        if (!missing.isEmpty()) {
            return new Gate(false, "missing-config-key", "credentials", List.copyOf(missing));
        }
        if (!liveOptIn) {
            return new Gate(false, "not-opted-in", "missing-live-opt-in", List.of());
        }
        return new Gate(true, "none", "gate", List.of());
    }

    // ---------------------------------------------------------------- §4 output

    /** 阶段结果（不含侧别/模式/键，仅格式化输入）。 */
    public record Execution(String result, String reason, String step, String code,
                            String requestId, int bytes, String sha256) {
    }

    public static Execution ok(String step, int bytes, String sha256) {
        return new Execution("ok", "none", step, "none", "none", bytes, sha256 == null ? "none" : sha256);
    }

    /** 成功但带显式 reason token（如 confirm-absent 的 {@code absent-confirmed}）。 */
    public static Execution okWithReason(String reason, String step, int bytes, String sha256) {
        return new Execution("ok", reason, step, "none", "none", bytes, sha256 == null ? "none" : sha256);
    }

    public static Execution fail(String reason, String step, int bytes, String sha256) {
        return new Execution("fail", reason, step, "none", "none", bytes, sha256 == null ? "none" : sha256);
    }

    public static Execution skipped(String reason) {
        return new Execution("skipped", reason, "skipped", "none", "none", -1, "none");
    }

    /** 契约 §4 的唯一定长行。 */
    public static String formatLine(String mode, String phase, Execution execution, String keyDigest,
                                    Redactor redactor) {
        return "[oss-smoke] side=" + SIDE
                + " mode=" + token(redactor.sanitize(mode), "none")
                + " phase=" + token(redactor.sanitize(phase), "none")
                + " step=" + token(redactor.sanitize(execution.step()), "none")
                + " result=" + token(redactor.sanitize(execution.result()), "none")
                + " reason=" + token(redactor.sanitize(execution.reason()), "none")
                + " code=" + token(redactor.sanitize(execution.code()), "none")
                + " requestId=" + token(redactor.sanitize(execution.requestId()), "none")
                + " bytes=" + execution.bytes()
                + " sha256=" + token(redactor.sanitize(execution.sha256()), "none")
                + " keyDigest=" + keyDigest
                + " purpose=" + PURPOSE;
    }

    public static String formatErrorLine(String phase, Throwable failure, Redactor redactor) {
        String exception = failure == null ? "none" : failure.getClass().getSimpleName();
        String message = failure == null ? "none" : failure.getMessage();
        return "[oss-smoke-error] side=" + SIDE
                + " phase=" + token(redactor.sanitize(phase), "none")
                + " exception=" + token(redactor.sanitize(exception), "none")
                + " message=" + singleLine(redactor.sanitize(message));
    }

    /** 错误消息保留可读空格，但压掉换行/制表符防日志注入。 */
    private static String singleLine(String value) {
        if (value == null || value.isBlank()) {
            return "none";
        }
        return value.replaceAll("[\\r\\n\\t]+", " ");
    }

    private static String token(String value, String emptyValue) {
        if (value == null || value.isBlank()) {
            return emptyValue;
        }
        return value.replaceAll("\\s+", "_");
    }

    /** 敏感值净化器：剔除 bucket/endpoint(+host)/完整 key/AK/SK/STS 及 LTAI 形态子串。 */
    public static final class Redactor {

        private final List<String> literals = new ArrayList<>();
        private final Pattern accessKeyPattern = Pattern.compile("LTAI[A-Za-z0-9]+");

        public static Redactor from(Args args, LiveConfig config) {
            Redactor redactor = new Redactor();
            if (args != null) {
                redactor.add(args.objectKey());
            }
            if (config != null) {
                redactor.add(config.bucket());
                redactor.add(config.endpoint());
                redactor.add(hostOf(config.endpoint()));
                redactor.add(config.accessKeyId());
                redactor.add(config.accessKeySecret());
                redactor.add(config.securityToken());
            }
            return redactor;
        }

        public Redactor add(String value) {
            if (value != null && !value.isBlank()) {
                literals.add(value);
            }
            return this;
        }

        public String sanitize(String message) {
            if (message == null) {
                return "none";
            }
            String out = message;
            for (String literal : literals) {
                out = out.replace(literal, "<redacted>");
            }
            out = accessKeyPattern.matcher(out).replaceAll("<redacted>");
            return out;
        }
    }

    static String hostOf(String endpoint) {
        if (endpoint == null || endpoint.isBlank()) {
            return null;
        }
        String value = endpoint.trim();
        int scheme = value.indexOf("://");
        if (scheme >= 0) {
            value = value.substring(scheme + 3);
        }
        int slash = value.indexOf('/');
        if (slash >= 0) {
            value = value.substring(0, slash);
        }
        return value;
    }

    // ---------------------------------------------------------------- §3 phases

    @FunctionalInterface
    public interface PublicUrlProbe {
        int probe(String endpoint, String bucket, String objectKey) throws Exception;
    }

    /** 阶段执行：只经 {@link StoragePort}；delete 只删传入的单个精确键。 */
    public static Execution executePhase(String mode, String phase, Args args, LiveConfig config,
                                         StoragePort storage, PublicUrlProbe probe) throws Exception {
        String key = args.objectKey();
        switch (phase) {
            case "write" -> {
                byte[] content = smokeBytes(args.contentSeed(), args.contentBytes());
                storage.put(key, new ByteArrayInputStream(content), content.length, CONTENT_TYPE);
                return ok("put", content.length, sha256Hex12(content));
            }
            case "verify" -> {
                if (!storage.exists(key)) {
                    // 验证阶段对象不存在 ⇒ 失败。token 用 object-missing（orchestrator 裁定）：
                    // absent-confirmed 只用于 confirm-absent 的**成功**语义，在失败行里复用它
                    // 会把失败读成成功；adapter-error 则掩盖"对象确定不存在"这一事实。
                    return fail("object-missing", "exists", -1, "none");
                }
                byte[] actual = storage.get(key);
                if (actual == null) {
                    return fail("adapter-error", "get-null", -1, "none");
                }
                byte[] expected = smokeBytes(args.contentSeed(), args.contentBytes());
                if (actual.length != expected.length) {
                    return fail("bytes-mismatch", "length", actual.length, sha256Hex12(actual));
                }
                if (!Arrays.equals(actual, expected)) {
                    return fail("sha-mismatch", "content", actual.length, sha256Hex12(actual));
                }
                return ok("get", actual.length, sha256Hex12(actual));
            }
            case "delete" -> {
                storage.delete(key);
                return ok("delete", -1, null);
            }
            case "confirm-absent" -> {
                if (storage.exists(key)) {
                    return fail("still-exists", "exists", -1, "none");
                }
                return okWithReason("absent-confirmed", "absent-confirmed", -1, null);
            }
            case "public-url-probe" -> {
                if (!"live".equals(mode)) {
                    return skipped("no-live-bucket");
                }
                int status = probe.probe(config.endpoint(), config.bucket(), key);
                if (status == 200) {
                    return fail("public-url-status-200", "public-url-status-" + status, -1, "none");
                }
                // step 只携带 HTTP 状态码；绝不打印 URL/bucket/key。
                return ok("public-url-status-" + status, -1, null);
            }
            default -> throw new IllegalArgumentException("unsupported phase: " + phase);
        }
    }

    /** 未鉴权公开 URL（仅用于探测；绝不打印其返回值）。 */
    public static URI publicUrl(String endpoint, String bucket, String objectKey) {
        String value = endpoint == null ? "" : endpoint.trim();
        String scheme = "https";
        int schemeIdx = value.indexOf("://");
        if (schemeIdx >= 0) {
            scheme = value.substring(0, schemeIdx).toLowerCase(Locale.ROOT);
            value = value.substring(schemeIdx + 3);
        }
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return URI.create(scheme + "://" + bucket + "." + value + "/" + objectKey);
    }

    // ---------------------------------------------------------------- run

    /** 由 runner 注入的存储构造（live 构造真实 OSS，double 构造文件替身）。 */
    public interface StorageFactory {
        StorageSession open(String mode, Args args, LiveConfig config) throws Exception;
    }

    public interface StorageSession {
        StoragePort port();

        void close();
    }

    /**
     * 完整编排（可单测）：解析参数 → 键校验 → 三重门 → 打开存储 → 执行阶段 → 输出。
     *
     * @return 进程退出码：成功 0、任何 fail/abort 非 0
     */
    public static int run(String[] argv, PrintStream out, boolean liveOptIn,
                          PublicUrlProbe probe, StorageFactory storageFactory) {
        Args args;
        try {
            args = parseArgs(argv);
        } catch (RuntimeException usageError) {
            out.println(formatErrorLine("none", usageError, new Redactor()));
            return 2;
        }
        Redactor parseRedactor = Redactor.from(args, null);
        if (!isValidObjectKey(args.objectKey())) {
            out.println(formatLine(args.mode(), args.phase(),
                    fail("invalid-object-key", "key-format", -1, "none"),
                    keyDigest(args.objectKey()), parseRedactor));
            return 2;
        }

        LiveConfig config = null;
        if ("live".equals(args.mode())) {
            try {
                config = loadYamlConfig(java.nio.file.Path.of(args.configPath()));
            } catch (Exception configFailure) {
                Redactor redactor = Redactor.from(args, null);
                out.println(formatLine(args.mode(), args.phase(),
                        fail("missing-config-key", "config", -1, "none"),
                        keyDigest(args.objectKey()), redactor));
                out.println(formatErrorLine(args.phase(), configFailure, redactor));
                return 2;
            }
        }

        Redactor redactor = Redactor.from(args, config);
        Gate gate = evaluateGate(args.mode(), config, liveOptIn);
        if (!gate.pass()) {
            out.println(formatLine(args.mode(), args.phase(),
                    fail(gate.reason(), gate.step(), -1, "none"),
                    keyDigest(args.objectKey()), redactor));
            if (!gate.missingKeys().isEmpty()) {
                // 只报缺失键名，绝不报其值。
                out.println(formatErrorLine(args.phase(),
                        new IllegalStateException("missing config keys: "
                                + String.join(", ", gate.missingKeys())), redactor));
            }
            return 2;
        }

        StorageSession session = null;
        try {
            session = storageFactory.open(args.mode(), args, config);
            Execution execution = executePhase(args.mode(), args.phase(), args, config,
                    session.port(), probe);
            out.println(formatLine(args.mode(), args.phase(), execution,
                    keyDigest(args.objectKey()), redactor));
            return "ok".equals(execution.result()) || "skipped".equals(execution.result()) ? 0 : 1;
        } catch (Exception adapterFailure) {
            out.println(formatLine(args.mode(), args.phase(),
                    fail("adapter-error", "exception", -1, "none"),
                    keyDigest(args.objectKey()), redactor));
            out.println(formatErrorLine(args.phase(), adapterFailure, redactor));
            return 1;
        } finally {
            if (session != null) {
                session.close();
            }
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}

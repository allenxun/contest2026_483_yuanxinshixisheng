package cn.yuanxin.mvp.web.testdouble;

import cn.yuanxin.mvp.web.media.MediaPurpose;
import cn.yuanxin.mvp.web.media.StoragePort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 对象存储测试替身（仅 dev/test）：本地文件系统，根目录
 * ${app.storage.dev-dir}（env APP_STORAGE_DEV_DIR 或 MVP_A_STORAGE_DEV_DIR，
 * 默认 /tmp/mvp-a-storage）。真实 OSS（最小权限凭据、私有桶）由部署配置替换。
 *
 * <p><b>跨语言布局约定</b>：文件路径 = <code>&lt;root&gt;/&lt;object_key&gt;</code>
 * 原样（key 含 "/" 时创建子目录），与 Python worker 的
 * FilesystemStorageDouble 字节一致——同一 root + 同一 key 两侧读写同一文件
 * （backend/tests/run-acceptance.sh 存储互操作步验证）。resolve 前
 * normalize + 根目录包含检查（防穿越）。</p>
 *
 * <p><b>受控失败注入（仅测试，默认关闭）</b>：{@code APP_DOUBLE_STORAGE_FAIL_MODE}
 * 控制 {@link #put} 是否抛受控 {@link UncheckedIOException}，供 SC-C-05 从真实
 * HTTP 入口驱动"上传/保存失败不得伪报成功"。取值：</p>
 * <ul>
 *   <li>{@code none}（默认）——不注入，行为与当前完全一致；</li>
 *   <li>{@code fail-put}——所有 purpose 的写入都失败（仅测试全局形态）；</li>
 *   <li>{@code fail-put:<purpose>[,<purpose>...]}——只让列出的 purpose 写入失败，
 *       例如 {@code fail-put:assessment_source} 只失败云台原图（M3-A01/A02），
 *       而 APP 授权/核验照片（{@code grant_face}，M1-A01）不受影响；</li>
 * </ul>
 * <p>purpose 取自服务端生成的 object key {@code <env>/<purpose>/<uuid>} 的第二段，
 * 与 {@link MediaPurpose#dbValue()} 对齐。<b>非法取值在构造（装配）期 fail fast</b>，
 * 绝不静默忽略。此开关只在 {@code TestDoubleProvidersConfig}（dev/test profile）
 * 内接线，生产 fail-closed 下不可达。</p>
 */
public class FileSystemStorageDouble implements StoragePort {

    /** 默认（关闭注入）。 */
    public static final String FAIL_MODE_NONE = "none";
    /** 全局失败前缀。 */
    public static final String FAIL_MODE_FAIL_PUT = "fail-put";

    private static final Logger log = LoggerFactory.getLogger(FileSystemStorageDouble.class);

    private final Path root;
    private final boolean failAllPuts;
    private final Set<String> failPurposes;

    public FileSystemStorageDouble(String devDir) {
        this(devDir, FAIL_MODE_NONE);
    }

    /**
     * @param devDir   存储根目录
     * @param failMode {@code none} / {@code fail-put} / {@code fail-put:<purpose>[,<purpose>...]}
     * @throws IllegalArgumentException 非法取值（装配期 fail fast）
     */
    public FileSystemStorageDouble(String devDir, String failMode) {
        this.root = Path.of(devDir).toAbsolutePath().normalize();
        String normalized = (failMode == null || failMode.isBlank())
                ? FAIL_MODE_NONE : failMode.trim().toLowerCase(Locale.ROOT);
        if (FAIL_MODE_NONE.equals(normalized)) {
            this.failAllPuts = false;
            this.failPurposes = Set.of();
        } else if (FAIL_MODE_FAIL_PUT.equals(normalized)) {
            this.failAllPuts = true;
            this.failPurposes = Set.of();
        } else if (normalized.startsWith(FAIL_MODE_FAIL_PUT + ":")) {
            String list = normalized.substring((FAIL_MODE_FAIL_PUT + ":").length()).trim();
            if (list.isEmpty()) {
                throw invalidFailMode(failMode, "empty purpose list");
            }
            Set<String> purposes = new LinkedHashSet<>();
            for (String raw : list.split(",")) {
                String purpose = raw.trim();
                if (!isKnownPurpose(purpose)) {
                    throw invalidFailMode(failMode, "unknown purpose '" + purpose
                            + "' (allowed: " + allowedPurposes() + ")");
                }
                purposes.add(purpose);
            }
            this.failAllPuts = false;
            this.failPurposes = Set.copyOf(purposes);
        } else {
            throw invalidFailMode(failMode, "expected none | fail-put | fail-put:<purpose>[...]");
        }
        if (failAllPuts || !failPurposes.isEmpty()) {
            // 仅装配期/启动日志（不含任何 token/PII），供 E 确认 env 旋钮已在进程内生效。
            log.warn("storage test-double write-failure injection ARMED:"
                    + " APP_DOUBLE_STORAGE_FAIL_MODE failAllPuts={} failPurposes={}",
                    failAllPuts, failPurposes);
        }
    }

    @Override
    public void put(String objectKey, InputStream content, long byteSize, String contentType) {
        if (shouldFailPut(objectKey)) {
            // 沿用既有异常类型（UncheckedIOException），使 MediaIntakeService 的
            // 既有映射（catch RuntimeException → 503 DEPENDENCY_UNAVAILABLE）原样生效。
            throw new UncheckedIOException("injected storage put failure"
                    + " (" + "APP_DOUBLE_STORAGE_FAIL_MODE" + ", purpose="
                    + purposeOf(objectKey) + ")",
                    new IOException("injected storage put failure"));
        }
        Path target = resolve(objectKey);
        try {
            Files.createDirectories(target.getParent());
            Files.copy(content, target, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            throw new UncheckedIOException("storage put failed", e);
        }
    }

    @Override
    public InputStream getStream(String objectKey) {
        Path p = resolve(objectKey);
        if (!Files.isRegularFile(p)) {
            return null;
        }
        try {
            return new ByteArrayInputStream(Files.readAllBytes(p));
        } catch (IOException e) {
            throw new UncheckedIOException("storage read failed", e);
        }
    }

    @Override
    public byte[] get(String objectKey) {
        Path p = resolve(objectKey);
        try {
            return Files.isRegularFile(p) ? Files.readAllBytes(p) : null;
        } catch (IOException e) {
            throw new UncheckedIOException("storage read failed", e);
        }
    }

    @Override
    public boolean exists(String objectKey) {
        return Files.isRegularFile(resolve(objectKey));
    }

    @Override
    public void delete(String objectKey) {
        try {
            Files.deleteIfExists(resolve(objectKey));
        } catch (IOException e) {
            throw new UncheckedIOException("storage delete failed", e);
        }
    }

    /** 当前是否对所有 purpose 注入写入失败（测试可观测）。 */
    public boolean failAllPuts() {
        return failAllPuts;
    }

    /** 当前注入写入失败的 purpose 集合；全局形态返回空集（测试可观测）。 */
    public Set<String> failPurposes() {
        return failPurposes;
    }

    private boolean shouldFailPut(String objectKey) {
        if (failAllPuts) {
            return true;
        }
        return !failPurposes.isEmpty() && failPurposes.contains(purposeOf(objectKey));
    }

    /** object key 布局 {@code <env>/<purpose>/<uuid>}：取第二段 purpose。 */
    private static String purposeOf(String objectKey) {
        if (objectKey == null) {
            return null;
        }
        String[] parts = objectKey.split("/");
        return parts.length >= 2 ? parts[1] : null;
    }

    private static boolean isKnownPurpose(String purpose) {
        for (MediaPurpose p : MediaPurpose.values()) {
            if (p.dbValue().equals(purpose)) {
                return true;
            }
        }
        return false;
    }

    private static String allowedPurposes() {
        return Arrays.stream(MediaPurpose.values()).map(MediaPurpose::dbValue)
                .sorted().collect(Collectors.joining(", "));
    }

    private static IllegalArgumentException invalidFailMode(String value, String reason) {
        return new IllegalArgumentException("invalid APP_DOUBLE_STORAGE_FAIL_MODE='" + value
                + "': " + reason + "; allowed: none | fail-put | fail-put:<purpose>[,<purpose>...]"
                + " where <purpose> ∈ {" + allowedPurposes() + "}");
    }

    private Path resolve(String objectKey) {
        Path p = root.resolve(objectKey).normalize();
        if (!p.startsWith(root)) {
            throw new IllegalArgumentException("object key escapes storage root");
        }
        return p;
    }
}

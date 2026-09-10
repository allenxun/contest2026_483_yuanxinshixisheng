package cn.yuanxin.mvp.web.testdouble;

import cn.yuanxin.mvp.web.media.StoragePort;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

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
 */
public class FileSystemStorageDouble implements StoragePort {

    private final Path root;

    public FileSystemStorageDouble(String devDir) {
        this.root = Path.of(devDir).toAbsolutePath().normalize();
    }

    @Override
    public void put(String objectKey, InputStream content, long byteSize, String contentType) {
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

    private Path resolve(String objectKey) {
        Path p = root.resolve(objectKey).normalize();
        if (!p.startsWith(root)) {
            throw new IllegalArgumentException("object key escapes storage root");
        }
        return p;
    }
}

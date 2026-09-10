// 单文件源码启动器（java -cp backend/web-java/target/classes StorageInterop.java ...），
// 直接驱动真实的 Java FileSystemStorageDouble，验证跨语言存储布局约定：
//   文件路径 == <root>/<object_key>（原样），与 Python FilesystemStorageDouble 一致。
// 用法:
//   put <root> <objectKey> <content>   # 经 Java double 写入（走 put()/存储目录创建）
//   get <root> <objectKey>             # 经 Java double 读取原始字节到 stdout；缺失退出码 4
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class StorageInterop {

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        String root = args[1];
        String key = args[2];
        FileSystemStorageDouble storage = new FileSystemStorageDouble(root);
        switch (mode) {
            case "put" -> {
                byte[] content = args[3].getBytes(StandardCharsets.UTF_8);
                storage.put(key, new ByteArrayInputStream(content), content.length,
                        "application/octet-stream");
                System.err.println("java_put_ok " + key);
            }
            case "get" -> {
                byte[] data = storage.get(key);
                if (data == null) {
                    System.err.println("java_get_missing " + key);
                    System.exit(4);
                }
                System.out.write(data);
                System.out.flush();
                System.err.println("java_get_ok " + key + " " + data.length + "B");
            }
            default -> {
                System.err.println("usage: StorageInterop <put|get> <root> <key> [content]");
                System.exit(2);
            }
        }
    }
}

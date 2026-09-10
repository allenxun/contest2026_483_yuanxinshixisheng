package cn.yuanxin.mvp.web.media;

import java.io.InputStream;

/**
 * 对象存储适配端口（digest §6 OSS 适配端口 / §7）。私有对象、purpose 驱动、
 * Web/Worker 最小权限凭据；PG 只存引用/归属，不存二进制。
 *
 * <p>dev/test 替身 = 本地文件系统（FileSystemStorageDouble）；
 * 生产 fail closed：无真实实现则启动失败（ProductionFailClosedValidator）。</p>
 */
public interface StoragePort {

    /** 写入对象（流式；实现负责限制大小与异常时清理临时状态）。 */
    void put(String objectKey, InputStream content, long byteSize, String contentType);

    /** 流式读取（对象不存在返回 null；调用方负责关闭）。 */
    InputStream getStream(String objectKey);

    byte[] get(String objectKey);

    boolean exists(String objectKey);

    void delete(String objectKey);
}

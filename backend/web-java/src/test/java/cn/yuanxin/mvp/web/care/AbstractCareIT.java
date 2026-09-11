package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.support.AbstractWebIT;
import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.test.context.TestPropertySource;

import java.util.UUID;

/**
 * C 包集成测试基类：在 A 的 {@link AbstractWebIT} 之上把测试存储根覆盖到本
 * 工作树 gitignored 运行目录 {@code target/c-test-storage}（bucket
 * {@code mvp-c-test}），产生独立 Spring 上下文（缓存键不同；时长代价已接受）。
 *
 * <p>不修改任何 A 公共文件；A 自身测试仍用 {@code /tmp/mvp-a-test-storage}。
 * {@link cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble#put} 会自动
 * {@code Files.createDirectories(parent)}，故根目录无需预建。</p>
 *
 * <p>同时提供人脸成员绑定替身的注入与用例级复位：默认未绑定 ⇒
 * CAPABILITY_UNAVAILABLE（fail-closed）；快乐路径须显式 {@link #bindFaceMember}。</p>
 */
@TestPropertySource(properties = {
        "app.storage.dev-dir=target/c-test-storage",
        "app.storage.bucket=mvp-c-test"
})
public abstract class AbstractCareIT extends AbstractWebIT {

    @Autowired
    protected MemberBindingFaceDouble faceDouble;

    @Value("${app.storage.dev-dir}")
    protected String storageDevDir;

    /** 绑定唯一可信目标成员（1:1 核验通过的前提）。 */
    protected void bindFaceMember(UUID memberId) {
        faceDouble.bindMember(memberId);
    }

    @AfterEach
    void resetCareFaceDouble() {
        faceDouble.reset();
    }
}

package cn.yuanxin.mvp.web.testsupport;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * test profile 专用：触发未映射异常，验证 advice → 500 INTERNAL
 * （客户端拿不到堆栈）与 requestId 透出。不随 jar 发布（src/test）。
 */
@RestController
@Profile("test")
public class TestErrorController {

    @GetMapping("/internal-test/boom")
    public String boom() {
        throw new IllegalStateException("simulated unexpected failure");
    }
}

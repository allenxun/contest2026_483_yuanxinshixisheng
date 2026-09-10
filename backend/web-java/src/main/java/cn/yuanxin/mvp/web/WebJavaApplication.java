package cn.yuanxin.mvp.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * MVP Web 后端入口（Spring MVC servlet 栈）。
 * 控制器、错误处理与公共设施由后续 lane 添加；此处仅保证应用可启动并提供 actuator 健康端点。
 */
@SpringBootApplication
public class WebJavaApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebJavaApplication.class, args);
    }
}

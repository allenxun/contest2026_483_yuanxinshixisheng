# HTTPS 客户端最小候选交接

本目录已独立实现纯 openvela/RK3576 可接入的 HTTPS/1.1 客户端候选，未修改正式源码、SDK、设备、串口、虚拟机或中央日志。范围只包含 TLS 传输适配和 HTTP 请求/响应；不包含 DNS、MiMo 契约、ASR/TTS 或 Agent 业务。

核心接口是 `include/vv_https_client.h`。请求体通过带 offset 的回调分块读取，适合后续 JSON 或音频；响应的 Content-Length、chunked 和连接关闭定界都按分片送入有界 sink。总期限采用单个绝对单调时钟 deadline，connect/read/write 共用；取消 token 同样贯穿三阶段。任何路径在已连接后失败都会关闭传输。

`src/vv_https_mbedtls.c` 固定使用 `MBEDTLS_SSL_VERIFY_REQUIRED`、调用 `mbedtls_ssl_set_hostname`、加载调用方限定的 CA bundle，并在握手后再次要求证书存在且 verify flags 为零。创建 DRBG 之前和每次连接之前都会调用 `security_ready`；RK3576 合格熵或可信墙钟任一未就绪就拒绝。TCP connector 由共享网络服务提供并负责 DNS、非阻塞连接、期限和取消，本候选没有另写 DNS。

HTTP 层限制生成请求头、响应头/尾、响应总 body 和单 chunk。它拒绝 CR/LF 注入、冲突 Content-Length、Content-Length 与 chunked 并存、非纯 chunked 的 Transfer-Encoding、截断、超限以及 1xx/204/304 非法 body。日志接口只收到固定事件名和数值；生成的头（含 Authorization 副本）与请求 staging 在退出前清零。原始 key/请求源仍归调用方清零。

主机假 TLS/传输测试在 GCC O0/O2、`-Wall -Wextra -Werror` 下均通过 9 组，覆盖分片 Content-Length、带扩展和 trailer 的 chunked、协议拒绝、body/chunk 上限、TLS 校验门、连接前取消/超时、sink 失败清理、header 注入和 EOF body。原始输出见 `evidence/host-tests.txt`；复现运行 `run_host_tests.ps1`。

`Kconfig`、`config/https-client.fragment` 和 `integration.cmake` 给出候选接入点。配置片段尚未在目标 SDK 运行 olddefconfig；Mbed TLS adapter 也尚未 ARM64 编译/链接或真机运行，不能视为 HTTPS 已上板。

真机前仍必须完成：RK3576 密码学熵、可信且防回退墙钟、准确 CA 根及轮换资料、目标 SDK olddefconfig/ARM64 构建、共享网络会话取消接线、错误 CA/域名/时间负测、受控 HTTPS endpoint framing 测试、20 次堆/栈回收测量及无线共存。满足这些门禁前不得带真实 API key；之后也只能先用 RAM 注入的最小权限可吊销测试 key。

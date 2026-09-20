# DNS 客户端候选交接

候选位于本目录，正式仓库源码和 SDK 均未修改。核心 API/实现分别是
`include/vv_dns_client.h` 和 `src/vv_dns_client.c`；NuttX 适配是
`include/vv_dns_nuttx.h`、`src/vv_dns_nuttx.c`；配置片段是
`config/dnsclient.fragment`。

主机假解析器在 O0/O2 下均通过 9 项。原始结果见 `test-results.txt`，文件
摘要见 `SHA256SUMS.txt`。接入和限制详见 `README.md`。

下一步应先在新的独立 SDK 构建目录合入配置并运行 `olddefconfig`，编译本
候选，核对 `getaddrinfo/freeaddrinfo` 强符号与最终 Kconfig；不要覆盖已验收
镜像。之后才把 DHCP option 6 登记和网络关闭清理接入正式 `k7radio`，再用
新的 OTG RAM 镜像做无凭据 DNS 探针。

ARM64 构建、真机 DNS、正式接线、MiMo 官方主机名核实均未完成。没有实现
HTTPS 或 Agent，没有访问设备、串口、VM、中央日志，也没有写入凭据。

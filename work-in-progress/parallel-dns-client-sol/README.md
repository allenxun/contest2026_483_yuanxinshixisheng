# RK3576 DNS 客户端最小候选

本目录是纯 openvela/NuttX IPv4 DNS 候选，只负责在 Wi-Fi 已取得 DHCP
租约后把一个经过批准的主机名解析成 IPv4 地址。它不实现 HTTPS、MiMo
协议或 Agent，不包含服务主机名和凭据，也没有修改正式源码或 SDK。

## 接口和边界

公开接口在 `include/vv_dns_client.h`：

```c
enum vv_dns_status vv_dns_resolve_ipv4(
  const char *hostname,
  const struct vv_dns_policy *policy,
  const struct vv_dns_backend *backend,
  struct vv_dns_result *result);
```

`result.ipv4_be` 是网络字节序 IPv4。结果还包含实际调用次数和原始
`getaddrinfo()` 错误码，但候选本身不打印主机名、地址或错误内容。调用方
也不应记录未来的 Authorization header、请求正文或凭据。

建议首轮策略是总期限 4500 ms、重试退避 100 ms、最多 2 次调用。只有
`VV_DNS_TEMPORARY_FAILURE` 会重试；不存在的名称、无 IPv4、系统错误、
取消和期限耗尽立即返回。主机名限制为 128 字节，逐标签限制为 63 字节，
只接受 ASCII 字母、数字、连字符和点。

`src/vv_dns_client.c` 是与系统无关的策略核心。`src/vv_dns_nuttx.c` 是
NuttX `getaddrinfo(AF_INET)` 适配器。NuttX `getaddrinfo()` 没有单次调用
超时参数，所以硬上限由 `config/dnsclient.fragment` 的发送超时、接收超时
和 resolver 重试数提供。适配器在剩余预算小于该编译期单次上限时拒绝
开始新的查询；返回后核心再次检查总期限。取消标志只能阻止下一次调用或
在调用返回后终止，不能抢占正在运行的 `getaddrinfo()`。

这个同步调用必须运行在独立云端任务，不能放进 `fw_wifi_ip_worker()`、
BLE 回调或持有共享无线 broker 锁的路径，否则 DNS 自己需要的 RX/TX
轮询会被饿死。首轮只允许一个调用者；NuttX 适配器使用一个静态上下文。

## 正式接入点（尚未修改）

1. 在 `app/k7radio/skw_netdev.c` 的 `skw_netdev_dhcp_status()` 中，IP、
   netmask 和 router 都成功设置后，验证 `state.dnsaddr.s_addr != 0`，再调用
   `netlib_set_ipv4dnsaddr(&state.dnsaddr)`。设置失败时不要把租约标为已应用。
2. 在同文件 `skw_netdev_close()` 清理 IP/router/netmask 的同一网络会话
   中调用 `netlib_cleardnsaddr()`，避免切换网络后使用旧 DNS。DHCP 没有
   option 6 时返回明确的未配置状态，不把网关猜成 DNS。
3. 把本候选的两个头文件和两个源文件迁入未来正式云端组件；云端任务在
   共享 Wi-Fi 服务报告在线并持有在线租约后初始化 NuttX backend，再调用
   `vv_dns_resolve_ipv4()`。链路丢失时设置取消标志。
4. MiMo 主机名必须来自后续核实的官方非秘密配置。当前仓内没有该契约，
   本候选没有猜测或硬编码名称。

候选 DNS 配置在 `config/dnsclient.fragment`。它要求 DHCP 运行期提供唯一
nameserver，关闭默认地址，并把单次 resolver 配置约束为 1 秒发送、1 秒
接收、1 次 resolver 尝试。合入前必须对派生 defconfig 运行
`olddefconfig` 并保存最终 `.config`；当前片段尚未经过 ARM64 配置解析。

## 主机复现

在 Windows PowerShell 中：

```powershell
cd E:\openvela\VelaVision\work-in-progress\parallel-dns-client-sol
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_host_tests.ps1
```

测试使用完全离线的假解析器，不访问真实 DNS。`-O0` 和 `-O2` 各覆盖：
首次成功、临时失败后成功、永久失败不重试、临时失败达到重试上限、后端
耗尽期限、退避耗尽期限、调用前取消、成功却无 IPv4、非法主机名/策略。

## 尚未完成

- 未在 `/home/swl/openvela` 对 NuttX 适配器做 ARM64 编译、链接或
  `olddefconfig`，未记录实际 resolver 符号和镜像体积差。
- 未修改正式 `k7radio` DHCP DNS 登记/清理路径。
- 未在 RK3576 RAM 镜像上解析真实域名；未测试 DHCP DNS、NXDOMAIN、
  超时、断网、切换网络和 Wi-Fi/BLE 共存。
- 未核实 MiMo API 的官方主机名，也未实现 TCP、TLS、HTTP 或 Agent。

上述项目完成前，本候选只能证明主机侧策略，不能声称 ARM64 构建或真机
DNS 可用。

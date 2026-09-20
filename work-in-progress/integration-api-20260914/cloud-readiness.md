# K7 cloud DNS/HTTPS 真机就绪审计

审计日期：2026-09-14。范围仅为 `app/k7agent/cloud`、当前 K7 无线接线、
`velavision_cloud_probe_local` 配置和已有构建证据；未运行网络或硬件，未读取或
写入密钥。当前结论是：组件已达到“主机策略测试 + ARM64 编译链接”阶段，尚未
达到板端 HTTP、DNS、TLS 或 MiMo 运行就绪。

## 现成代码可复用清单

| 组件 | 可直接复用的能力 | 当前证据 | 真机边界 |
|---|---|---|---|
| `vv_dns_client` | 主机名上限、IPv4 单结果、总期限、取消、临时失败重试及明确失败码 | DNS O0/O2 各 9 项通过；正式 ARM64 镜像已保留 DNS 强符号 | DHCP DNS 尚未登记，板端从未解析域名；NuttX backend 是单个静态上下文，首版只能串行使用 |
| `vv_dns_nuttx` | `getaddrinfo(AF_INET)`、`EAI_*` 映射、编译期 resolver 调用上限 | `velavision_cloud_probe_local` 已启用 `LIBC_NETDB` 和 `NETDB_DNSCLIENT`，收发超时各 1 秒、resolver retries=1 | `getaddrinfo()` 不能被运行时抢占；取消只能在调用前后生效，真正上限仍依赖最终 `.config` |
| `vv_https_client` | 有界 HTTP/1.1 请求头、响应头、Content-Length、chunked/eof body、总期限、取消、sink、临时缓冲清零 | HTTPS O0/O2 各 9 组通过；ARM64 已链接 | `vv_https_perform()` 在传输连接后强制 SNI、peer cert 和 `verify_flags==0`，因此不能直接用于明文 HTTP |
| `vv_https_mbedtls` | TLS client、SNI、`VERIFY_REQUIRED`、CA parse、CTR-DRBG、非阻塞握手/读写的 50 ms poll 切片、关闭与清理 | Mbed TLS 组件及适配器已编译链接 | 构造函数仍要求调用者提供 CA、TCP connector 和 `security_ready()`；这些板端实现均不存在 |
| `mimo_cloud_client` / `mimo_v25_profile` | MiMo v2.5 非流式 ASR/TTS Chat Completions 编码、Base64、严格嵌套 JSON 解码、WAV 校验、有界输出和敏感缓冲清理 | O0/O2 各 12 组通过，新增源做过隔离 ARM64 编译 | `EXAMPLES_K7CLOUD_MIMO_V25` 默认关闭，cloud probe 配置未启用；没有运行时 endpoint/token 注入或板端调用入口 |
| `k7radio` IPv4 数据面 | WPA2、DHCP、IPv4、UDP/TCP socket 和持续约 5 ms 的网络轮询已有历史真机证据 | 历史 Wi-Fi/DHCP/网关短测通过 | 当前设备快照离线；云端调用必须在独立任务运行，不能阻塞 `fw_wifi_ip_worker()` |
| `k7cloud` 命令 | 保留组件并执行无网络的参数校验 | `k7cloud status` 输出 linked/selftest | 命令明确输出 `network_request=disabled`，没有 DNS、TCP、HTTP、TLS 或 MiMo probe |

相关验收入口是 `evidence/k7cloud-link-20260913/acceptance.json`。其范围明确是
主机测试和独立 ARM64 编译链接，`board_tested`、`dns_runtime_tested`、
`https_runtime_tested` 都为 false。

## 当前板端缺口

- **网络租约与 DNS：**`skw_netdev_dhcp_status()` 只设置 IPv4、netmask 和
  default router，没有把 `dhcpc_state.dnsaddr` 交给
  `netlib_set_ipv4dnsaddr()`；`skw_netdev_close()` 也没有
  `netlib_cleardnsaddr()`。共享服务没有包含 generation、link/DHCP 状态、
  IPv4、gateway、DNS 的只读快照，断链无法可靠取消旧代次云端请求。
- **TCP：**仓内没有满足 `vv_https_tcp_connect_fn` 的实现。需要 NuttX IPv4
  非阻塞 connector：`socket` → `O_NONBLOCK` → `connect` → 对
  `EINPROGRESS` 以不超过 50 ms 的 `poll(POLLOUT)` 切片等待 →
  `getsockopt(SO_ERROR)`；每个切片检查绝对 monotonic deadline、显式取消和
  lease generation，失败关闭 fd。read/write 也必须有同样的 poll/cancel 边界。
- **entropy：**cloud probe 的 `DEV_URANDOM` 关闭，RK3576 arch 目录没有 RNG
  driver。`app/k7radio/skw_random.c` 有基于蓝牙控制器 `LE_Rand` 的 Wi-Fi
  专用候选，但它尚未接入 NuttX random/mbedTLS entropy，依赖 HCI 生命周期，
  也没有完成重启分离、重复块、健康检测和故障传播验收，不能直接把
  `security_ready` 置 true；禁止回退到时间戳、MAC、`rand()` 或 xorshift。
- **可信时间：**cloud probe 中 `CLOCK_TIMEKEEPING=n`、`RTC=n`，启动日期固定
  为 2026-09-01。`CLOCK_MONOTONIC` 足够做 deadline，不足以校验 X.509
  NotBefore/NotAfter。现有 RTC 状态诊断不是 NuttX 可信墙钟适配。需要可检测未设置
  和回退的 UTC 来源，并在 TLS 前 fail closed。
- **CA：**正式目录没有 PEM/DER 根证书。需要等待生产 HTTPS hostname 和实际
  证书链，选择最小根集合，记录 subject/serial/有效期/SHA-256，并预留双根轮换；
  不能用 `VERIFY_NONE`、自签临时根或叶证书 pin 代替生产策略。
- **HTTP authority：**`vv_https_client.c::make_headers()` 当前 `Host` 只写
  `q->host`，不会为显式非默认端口追加 `:port`，同时禁止调用者覆盖 Host。
  `10.3.3.170:18085` 的正确 authority 必须是 `Host: 10.3.3.170:18085`。
- **整合配置和入口：**目前 cloud probe 不含 MiMo v2.5，最新语音主线也不是已验收
  的 combined speech+cloud 镜像。需要从稳定的语音/无线配置派生新 RAM-only
  revision，重新检查 Kconfig、ELF、堆/栈和 OTG 包上限；不能把旧 cloud-only
  构建结论套到新镜像。

## 访问 `10.3.3.170:18085` 的最短路径

这个地址是明文 HTTP 和字面 IPv4。第一轮应限定为无凭据开发探针，它不需要 DNS、
Mbed TLS、entropy、可信墙钟或 CA，也不能算 DNS/TLS 验收。板端地址与目标是否有
跨子网路由仍需实测；已有 `10.3.0.214/24` 快照不能证明 `10.3.3.170` 可达。

1. 先补只读 lease snapshot/generation，并让断链或 generation 变化触发取消；保留
   `fw_wifi_ip_worker()` 持续 pump，探针运行在独立 `k7cloud` 任务。
2. 实现上述共享的 `vv_tcp_nuttx` 非阻塞连接器。对本地址用 `inet_pton(AF_INET)`，
   直接连接 `10.3.3.170:18085`，完全绕过 DNS。
3. 从现有 `vv_https_client` 提取不含证书判定的有界 HTTP/1.1 framing 核心，并保留
   两个显式 wrapper：`vv_http_perform(..., PLAIN_DEV_ONLY)` 与现有
   `vv_https_perform(..., TLS_REQUIRED)`。HTTPS wrapper 继续强制 SNI/cert/flags；
   禁止让明文 transport 伪造 `peer_verified=true`。
4. 修正 authority 生成：显式非默认端口写入 `Host: 10.3.3.170:18085`。首个命令只
   做 `k7cloud http-probe`，总期限建议 5 秒、connect 最多 2 秒、响应头 8 KiB、
   body 64 KiB、chunk 16 KiB，单次请求、无自动重试、无重定向。
5. 后端需给出一个明确允许无凭据访问的 health/docs 路径和预期状态码后再发请求；
   当前 OpenAPI 没有 health path。若只验证 L4，可先做 connect/close。不要用设备
   credential、session token 或任何业务正文测试明文链路。

如果只追求一次诊断而不想先抽取 framing，可写一个极小、固定 GET 的 raw HTTP probe；
它只能用于 L3/L4/HTTP 状态验证，不能成为业务客户端。共享 framing + 双 wrapper 的
改动稍多，但避免复制 response parser，也不会削弱后续 HTTPS 的 fail-closed 门禁。

## 之后访问 HTTPS MiMo 的最短路径

1. 完成 lease generation、DHCP option 6 登记/清理和板端 DNS probe；正式 hostname
   不允许固定 IP 回退。
2. 复用同一个 `vv_tcp_nuttx`，但输入来自 DNS 解析的 IPv4；保留绝对 deadline、
   取消、`SO_ERROR` 检查和断链 close。
3. 先完成 entropy、可信 UTC 和 endpoint 对应最小 CA 的独立验收，再让
   `security_ready()` 同时检查三项。任一未就绪都不得 seed DRBG 或发起 TLS。
4. 用 `vv_https_mbedtls` 做无 Authorization 的 TLS/HTTP probe：必须有 SNI、peer
   certificate、hostname/有效期/链校验成功且 flags=0；错误 hostname、错误 CA、
   过期/未来时间必须失败。记录版本、cipher、耗时和数值错误，不记录响应正文。
5. 核实运行时 MiMo Token Plan 的准确 hostname/region 后再启用
   `EXAMPLES_K7CLOUD_MIMO_V25`。复用现有非流式 codec 和 `mimo_cloud_client`，先做
   单请求、严格 body/response 上限及清理检查；endpoint 与 token 必须成对从 RAM
   注入，不能写入 Git、defconfig、固件字符串、命令行或串口。
6. 产品优先路径应是 K7 通过生产 HTTPS 访问自有后端，由后端保管 MiMo 上游 secret；
   K7 只持短期 device session。若决定让 K7 直连 MiMo，则设备唯一安全存储、token
   轮换/吊销和崩溃转储边界是额外门禁，当前只读 eMMC 路径不满足该条件。

## 最小验收顺序

| 阶段 | 通过条件 | 当前状态 |
|---|---|---|
| H0：内网 TCP | connect/close 在 2 秒内完成；断链/取消有界关闭 | 未实现、未实测 |
| H1：无凭据 HTTP | 正确 Host authority；预期状态码；响应不超限；5 秒内结束 | framing 可复用，plain wrapper/transport 缺失 |
| D1：DHCP DNS | 租约含 DNS；断网清除；generation 改变 | 未接线 |
| D2：域名解析 | 非零 IPv4；NXDOMAIN/超时/取消/重连不返回旧结果 | 核心已测，板端未测 |
| T1：信任前置 | 合格 entropy、可信 UTC、最小 CA 分别通过及负例通过 | 全部未完成 |
| T2：无密钥 TLS | SNI/cert/hostname/time/chain 通过且 flags=0；断链有界 | 适配已编译，TCP/runtime 未完成 |
| M1：MiMo codec | 精确 region/host；O0/O2 fixtures；正式 combined ARM64 构建 | codec 主机测试已过，配置/整合未完成 |
| M2：单次受限调用 | 2xx、输出有界、资源回收、证据无 token/audio/text | 未开始 |

在 H1 通过前只能称“云端组件可编译”；H1 通过只证明该明文开发地址可访问，不能
推出 DNS、互联网、TLS 或 MiMo 可用。T2 和 M2 必须绑定各自实际 RAM 镜像、最终
`.config`、CA 摘要及原始脱敏证据。

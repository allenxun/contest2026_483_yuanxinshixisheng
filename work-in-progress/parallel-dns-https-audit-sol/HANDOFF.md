# RK3576 DNS/HTTPS → 小米 MiMo API 最小路径审计

## 结论

当前 `audio-pause-20260911` 镜像已经有可用的原生 Wi-Fi IPv4 数据面、TCP、UDP、socket 选项、异步 DHCP 和持续收发轮询；历史真机证据证明过 WPA2、DHCP、网关首包和短时保持。它还不能访问域名或 HTTPS：`LIBC_NETDB`、`NETDB_DNSCLIENT`、`CRYPTO_MBEDTLS`、`NETUTILS_WEBCLIENT`、`NETUTILS_LIBCURL4NX`、`UTILS_CURL`、RTC、timekeeping 和 `/dev/urandom` 均未启用。

建议的最小实现是：保留 `k7radio` 的持续 Wi-Fi worker；在 DHCP 租约生效时登记 DHCP 下发的 DNS 地址；在独立云端任务中使用 NuttX `getaddrinfo()`、Mbed TLS 客户端和 `webclient`；为 `webclient_tls_ops` 写一个很薄的 Mbed TLS 适配层。SDK 没有现成的 `webclient_tls_ops` 实现。`libcurl4nx` 当前只实现 HTTP，不能作为 HTTPS 捷径。完整 curl 体量和依赖更多，不适合作为首个探针。

生产 HTTPS 目前有两个前置阻塞：RK3576 BSP 没有硬件 RNG 接入，系统也没有可靠的实时时钟。不能用默认 xorshift `/dev/urandom` 生成 TLS 随机数，也不能长期依靠编译时 `CONFIG_START_YEAR/MONTH/DAY` 做证书有效期校验。先解决这两个信任根，再放入任何真实 API key。

本地没有 MiMo API 的主机名、路径、模型、鉴权头、JSON/流式协议契约。本审计不猜这些值；接入时应从官方契约单独填入非秘密配置，真实 key 只在运行时注入。

## 已核实能力与缺口

| 层 | 当前状态 | 证据/影响 |
|---|---|---|
| Wi-Fi L2/L3 | 已有原生 `wlan0`、WPA2、A-MSDU RX、ARP、DHCP | `skw_netdev.c` 注册 Ethernet netdev；Wi-Fi worker 每约 5 ms 调用 `skw_netdev_poll()` |
| IPv4 socket | `NET_IPv4/TCP/UDP/SOCKOPTS=y` | 可做数字 IP TCP 探针；TCP/UDP 预分配连接各 8 |
| DHCP DNS | DHCP 客户端会解析 option 6 到 `dhcpc_state.dnsaddr` | 当前代码只设置 IP/netmask/router，丢掉了 `dnsaddr` |
| DNS resolver | SDK 内有 `getaddrinfo()`、DNS cache、`dns_add_nameserver()` | 当前 `LIBC_NETDB=n`、`NETDB_DNSCLIENT=n` |
| HTTP | SDK `webclient` 支持请求体、流式 sink、状态码、重定向与 TLS 操作向量 | 当前未启用；TLS 操作向量必须由应用提供 |
| TLS | SDK 已本地包含 Mbed TLS 3.4.0 源码，客户端、SNI、X.509、TLS 1.2/1.3 基础模块存在 | 当前 `CRYPTO_MBEDTLS=n`；默认配置还启用大量服务器/DTLS/旧算法，需后续按实测裁剪 |
| CA | 没有项目 CA bundle 或固定根证书 | 必须提供最小受信根集合与轮换策略，禁止 `VERIFY_NONE` |
| 熵 | RK3576 arch CMake 只列 boot/serial/USB/model arena，无 RNG 实现；`DEV_URANDOM=n` | Mbed TLS 在 NuttX 上调用 `getrandom()`，最终读取 `/dev/urandom`；直接启用会失败，启用默认 xorshift 又不安全 |
| 时间 | `RTC=n`、`CLOCK_TIMEKEEPING=n`，启动基准固定为 2026-09-01 | 证书日期校验没有可靠墙钟；实验可人工设时，产品需可防回退的可信时间方案 |
| MiMo 契约 | 仓内无本地资料 | 主机/路径/模型/鉴权/流式格式需另行锁定；不写 key 到源码 |

`CONFIG_TLS_*` 在现有项目里表示 NuttX/C++ 线程局部存储槽，和网络 TLS 没有关系。wpa_supplicant 目录里的 TLS 头也不能证明 HTTPS 可用；当前 WPA2-PSK 路径没有提供通用 HTTPS 客户端或公共 CA 验证。

## 最小配置候选

先从当前无线/语音 defconfig 派生一个独立配置，不覆盖已验收镜像。第一轮只加：

```text
CONFIG_LIBC_NETDB=y                 # 也会被下列选项 select
CONFIG_NETDB_DNSCLIENT=y
CONFIG_NETDB_DNSCLIENT_ENTRIES=2
CONFIG_NETDB_DNSCLIENT_NAMESIZE=128
CONFIG_NETDB_DNSCLIENT_MAXRESPONSE=512
CONFIG_NETDB_DNSCLIENT_RECV_TIMEOUT=5
CONFIG_NETDB_DNSCLIENT_SEND_TIMEOUT=5
CONFIG_NETDB_DNSCLIENT_RETRIES=2
CONFIG_NETDB_DNSSERVER_NAMESERVERS=1
CONFIG_NETDB_DNSSERVER_NOADDR=y     # 只接受运行期 DHCP DNS，不硬编码 10.0.0.1

CONFIG_CRYPTO_MBEDTLS=y
CONFIG_MBEDTLS_SSL_SRV_C=n
CONFIG_MBEDTLS_SSL_PROTO_DTLS=n
CONFIG_MBEDTLS_SSL_IN_CONTENT_LEN=16384
CONFIG_MBEDTLS_SSL_OUT_CONTENT_LEN=16384
CONFIG_NETUTILS_WEBCLIENT=y
```

上述是候选，不是已经过 `olddefconfig` 的最终片段。Mbed TLS Kconfig 默认打开很多模块；第一版保留 RSA、ECDSA、ECDH、P-256/P-384、X25519、AES-GCM、ChaCha20-Poly1305、SHA-256/384、SNI、X.509 解析与 TLS 1.2/1.3 客户端兼容性，先用真实服务握手确定协商结果，再关闭服务器、DTLS、PSK、PAKE、写证书、CRL、PSA 持久存储和未使用曲线/算法。不要一开始把输入 record 降到 4 KiB；服务器未协商 Max Fragment Length 时可能合法发送接近 16 KiB 的 TLS record。

不需要 `OPENSSL_MBEDTLS_WRAPPER`。不建议首轮启用 `NETUTILS_LIBCURL4NX`（其 URL 处理仅接受 HTTP）或完整 `UTILS_CURL`。

### DNS 接线

在 DHCP 回调复制的租约成功应用后，检查 `state.dnsaddr.s_addr != 0`，调用：

```c
netlib_set_ipv4dnsaddr(&state.dnsaddr);
```

接口关闭时调用 SDK 已有的 DNS 清理接口（`netlib_cleardnsaddr()`），防止切换网络后沿用旧 DNS。DNS 设置属于网络会话状态，必须和 IP/router 一起更新、一起清理。不要把网关自动当成 DNS；只在 DHCP 明确缺省且产品策略批准后使用显式备用 DNS。

### 任务与 socket 关系

HTTPS 不能在 `fw_wifi_ip_worker()`、BLE 回调或持有无线 broker 锁时执行。该 worker 必须继续约每 5 ms pump RX/TX；阻塞 DNS、TCP 或 TLS 放到同一任务会让自己的报文无法推进。云端请求应在独立任务运行，持有共享无线服务的在线租约，设置 DNS/connect/read/write 总期限，并在链路丢失或用户取消时关闭 socket。初始只允许一个并发 TLS 请求。

## TLS/CA/密钥边界

1. **熵源门禁**：优先接 RK3576 硬件 TRNG，向 NuttX 提供经过审查的 `ARCH_HAVE_RNG`/`DEV_RANDOM` 或 Mbed TLS hardware entropy source。BSP 未有实现，寄存器、clock/reset 和健康检测必须以芯片资料为准。禁止用 xorshift、MAC、时间戳、ADC 固定噪声或硬编码 seed 冒充加密熵。
2. **时间门禁**：TLS 前拒绝明显未初始化或回退的时间。实验镜像可在串口显式设置已知 UTC 做握手验证；产品路径应使用 RTC，或保存上次可信时间并结合单调时钟与经认证的服务时间更新。普通 NTP 只能帮助校时，不能单独成为防攻击信任根。
3. **服务端验证**：必须设置 SNI/hostname，加载限定 CA 根，并要求 `MBEDTLS_SSL_VERIFY_REQUIRED`；同时检查 handshake 返回值、verify flags 和主机名。错误 CA、错误域名、过期/未来时间都必须失败。
4. **CA 不是秘密**：可编译进只读镜像或从只读文件加载；只包含 MiMo 服务链需要的根，记录 DER/PEM SHA-256、主题、序列号、有效期，并预留双根轮换。不要只 pin 当前叶证书，除非已有明确轮换通道。
5. **API key 是秘密**：不得进入 Git、defconfig、固件常量、命令行参数、串口、崩溃转储、测试 evidence 或日志。当前 eMMC 仅完成只读路径，没有已验收的安全持久存储，因此第一阶段只允许 RAM 临时注入测试 key，重启即失效。正式 key 需要设备唯一安全存储、访问控制和轮换/吊销；做不到时应通过受控代理而不是把长期生产 key 固化在板上。
6. **内存擦除**：Authorization header、key 副本、请求体临时缓冲和 TLS secret context 在释放前显式清零；日志只记长度、状态、耗时和不可逆请求 ID，绝不记录 header/body 全文。
7. **传输策略**：只允许 HTTPS；重定向默认关闭，或只允许同一批准 hostname 的 HTTPS。限制响应头、响应体、chunk 长度和 JSON 深度；拒绝无限流和无界 Content-Length。

## Mbed TLS → webclient 适配最小接口

实现 `webclient_tls_ops` 的 `connect/send/recv/close/get_poll_info`：

- `connect`：`getaddrinfo`/socket 或 `mbedtls_net_connect`，设置 SNI (`mbedtls_ssl_set_hostname`)，绑定 CA 和 RNG，完成有总期限的 handshake，验证证书与 hostname。
- `send/recv`：把 `WANT_READ/WANT_WRITE` 映射成 `-EAGAIN`，其他错误映射为负 errno，同时保留经过脱敏的 Mbed TLS 错误码供诊断。
- `get_poll_info`：返回底层 fd 及读写兴趣，供 `WEBCLIENT_FLAG_NON_BLOCKING` 使用。
- `close`：尽力发送 close_notify，关闭 fd，free 全部上下文并清零秘密。

`webclient` 负责 HTTP/1.1 header、request body、sink 回调、状态码和 chunked body。MiMo 的 JSON 应增量生成到 body callback，响应通过 sink callback 增量送入有界解析器；不要拼接成无界整包。若官方协议要求 SSE，先以每行和单事件上限实现解析，再允许 `stream=true`。

## 内存预算与测量门禁

当前最近无线证据显示系统堆约 126.8 MiB 可用，但这不是给云端调用无限分配的理由；ASR 已使用独立模型池，不能挪用或混淆两者。首个单连接候选采用以下门禁：

| 项目 | 初始预算 |
|---|---:|
| 云端任务 stack | 32 KiB（实测 watermark 后再降） |
| TLS record buffers | 16 KiB in + 16 KiB out |
| CA 与证书链解析动态峰值 | 256 KiB 预算 |
| DNS/cache/header/控制结构 | 16 KiB 预算 |
| 请求 JSON staging | 16 KiB，上游增量输出 |
| 响应/SSE staging | 32 KiB，sink 增量消费 |
| 单次 HTTPS 额外系统堆峰值门禁 | 512 KiB |
| 固件 `nuttx.bin` 增量预警线 | 1.5 MiB；记录 map 后按实际裁剪 |

预算是验收上限，不是当前实测。构建后记录 `.text/.rodata/.bss` 差值；运行时在 DNS 前、TCP 后、TLS 后、首字节后、关闭后记录 heap 和 task stack watermark。关闭后 heap live 应回到基线容差 4 KiB，连续 20 次请求不得单调下降。模型推理与 TLS 第一轮分时运行，确认稳定后再做并发压力。

## 构建与运行探针顺序

每一步都使用新 revision、新构建目录和 OTG Fastboot RAM 启动；不刷 eMMC，不覆盖旧 artifact。

1. **配置探针**：运行 `olddefconfig`，保存最终 `.config`；编译只引用 DNS/Mbed TLS/webclient API 的空入口，审查 ELF 强符号为 0、镜像增量和 map。不得触设备。
2. **熵探针**：先完成真实硬件熵接入。冷启动多轮读取，检查 API 错误、全零/重复块、基本连续健康检测和故障注入；统计测试只发现明显故障，不能单独证明密码学安全。没有合格熵时停止。
3. **时间探针**：读取当前 UTC，验证未设置/回退会被拒绝；实验中显式设置已知时间并复读。没有可信时间时只能做标记为不安全的实验握手，不能带 key。
4. **DHCP DNS 探针**：打印脱敏后的 DNS 地址（地址可记录），调用 `getaddrinfo` 解析一个批准的测试域名；同时测不存在域名、超时、断网和网络切换清理。先不连 443。
5. **TCP 443 探针**：对 DNS 返回地址建立 TCP，记录地址族、耗时与 errno，不发 API 数据。
6. **TLS 探针**：只做 handshake/close。记录 TLS 版本、cipher suite、叶证书 SPKI/链摘要、verify flags、堆峰值；错误 CA、错误 hostname、错误时间必须失败。不得关闭验证绕过失败。
7. **HTTPS 回显探针**：对团队控制的 HTTPS endpoint 做小 POST，覆盖 Content-Length、chunked、分片 header、超时和断链；验证 webclient sink 有界。
8. **MiMo 无密钥协议探针**：按已锁定官方契约向真实 endpoint 发送无 key/假 key，期望明确 401/403；只验证 DNS/TLS/HTTP，不记录响应敏感正文。
9. **受限 key 单请求**：RAM 注入最小权限、可吊销测试 key，做一个最小非流式请求；验证状态码、JSON 上限、超时和 key 清零。完成后立即吊销或让临时 key 过期。
10. **流式与恢复**：若需要 SSE，再测事件分片、UTF-8 跨包、服务端错误、限流、取消和重连。随后做 20 次资源回收、30 分钟 Wi-Fi/BLE 共存和一次 ASR→云端串联；分别报告组件通过项与严格零丢包结果。

每一步的原始串口/构建日志必须绑定镜像 SHA-256、`.config` SHA-256、CA bundle SHA-256 和非秘密 API 配置摘要。真实 key 不进入哈希清单，因为它不应落盘。

## 失败即停止条件

- 熵源回退到 `DEV_URANDOM_XORSHIFT128` 或 RNG health check 失败。
- 系统时间未初始化、明显回退或无法验证证书有效期。
- `verify_result != 0`、hostname 不匹配、CA 缺失却仍继续请求。
- Wi-Fi worker 在 DNS/TLS 期间停止 pump，出现 RX queue 增长、A-MSDU reject 或链路 cleanup 竞态。
- Authorization/header/body 出现在串口、日志、core dump、固件 strings 或 evidence。
- 响应超预算、任务 stack watermark 越界、20 次后 heap 不回收。

## 输入与复核

`inputs.json` 固定了本次读取的项目文件、SDK 文件、大小、SHA-256，以及 NuttX/apps commit。`audit_inputs.py` 只读重算项目输入；在 VM 中加 `--sdk /home/swl/openvela` 可同时重算 SDK 输入并输出 Kconfig 状态。

```powershell
python work-in-progress/parallel-dns-https-audit-sol/audit_inputs.py --repo E:\openvela\VelaVision
```

```sh
python3 work/velavision-project/work-in-progress/parallel-dns-https-audit-sol/audit_inputs.py \
  --repo /home/swl/openvela/work/velavision-project --sdk /home/swl/openvela
```

本次只读访问 Ubuntu VM，没有下载任何网络依赖；没有修改 SDK、正式源码、设备、无线状态或其它候选。

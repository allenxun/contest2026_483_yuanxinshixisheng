# Wi-Fi 入网协议和 BLE 配网服务移植

统一工程后续更新：EAPOL 编解码实际开发入口已迁入 `../../app/k7radio/skw_wifi_eapol.h`，新增接收队列已编译接入。本文下方及本目录旧文件保留为阶段背景，最新状态见 [本轮接收链路进展](../../docs/WiFi-EAPOL接收进展_20260909.md)。

## 2026-09-09 最新状态（覆盖下方历史记录）

板端已运行 id36 原生 openvela。`prov_protocol.c/h`、`prov_service.inc` 已链接进该候选，自定义 BLE GATT 加密连接、X 扫描回传、10 次重连、100 次连续命令、两类会话中断恢复已通过；30 分钟长测结果以 `../frontend/测试结果.json` 和 `../evidence/ble-id36-client-endurance-01.jsonl` 为准，不能在出现最终 PASS 前算通过。

真实 Lansee 关联探针成功（status=0、AID=3），两次收到 153 字节数据包，32 字节前缀中出现本机/AP MAC 及 EtherType 0x888e。仅捕获前缀，没有捕获完整 EAPOL 主体，没有完成 WPA2 或获取 IP。证据为 `../evidence/wifi-association-id36.json`。

`skw_wifi_eapol.h` 是本次新准备的 **未链接进 id36** 的数据编解码层，已通过 ASan/UBSan、截断/错误地址/容量检查及 20,000 个畸形帧检查。测试使用实际描述符前缀加明确标注的合成主体，不能称为真实 WPA 握手验证。

GET_INFO 的私有能力位实际为 0x0100000c，`priv_pn_reuse` 已置位。官方 skw_rx_cb 在此模式下保留 SDIO 的 4 字节头，描述符覆盖从完整 slot 开始的 20 字节；本次 MSDU 起点为 raw slot +22（去掉 SDIO 头后的 payload +18），长度来自 desc.pn[4:6]，值 129，再加6得到135字节 Ethernet 帧。不要把已去掉4字节头的 payload 再当作描述符起点。

EAPOL 发包遵循官方 skw_core.c 的 ETH_P_PAE 分支，通过 `SKW_CMD_TX_DATA_FRAME=15` 的命令路径发送，前置6字节 TX 描述符和2字节配置，再接 Ethernet+EAPOL。这里只编码参数，尚未实测该 TX 路径；必须检查固件 ACK，不能把编码测试当作发送成功。

剩余工作是接入上游 WPA 状态机、完整 EAPOL RX/TX、真实随机源、定时器、密钥安装/清除，以及 netdev/DHCP。当前 `connect` 返回 `not_ready`。用户密码仍只保留本地私密配置，不进入源码、VM、共享日志或前端交付包。

## id30 阶段历史背景

当前板端验收基线仍是id30，Wi-Fi未联网。这里是后续集成用的源代码，未链接进当前镜像；不能将下述测试称为真机连接成功。

skw_wifi_join.h按官方skw_cfg80211.h、skw_cfg80211.c和skw_msg.c实现：

- JOIN 25字节固定头+完整beacon IE，显式小端和20MHz初始带宽；
- Open System认证14字节参数，这一步不使用Wi-Fi密码；
- ASSOC 54字节固定头+认证组件生成的关联IE；
- 4字节JOIN回复解码；
- event4中的认证/关联响应解码，验证目标BSSID、本机MAC、信道、帧长、认证事务号和结果码；
- 本机STA的DISCONNECT参数。

编译测试使用GCC -Wall -Wextra -Werror和ASan/UBSan，覆盖字段偏移、截断、错误返回、非目标设备、失败状态及20000个畸形帧。它不包含射频、连接状态机或加密握手模拟。

官方实际STA路径使用event4管理帧完成认证/关联；不能只等枚举中的event3/event7就认定连接成功。
skw_calib.h在未启用CONFIG_SWT6621S_CALIB_DPD时的DPD接口为空操作；官方当前Makefile也注释了对应对象。已有R0000校准仍必须按id30流程加载。

## WPA2接入位置

已从https://w1.fi/releases/wpa_supplicant-2.12.tar.gz下载官方源码至../upstream-wpa，902个文件。
SHA256：08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6。
PGP签名已下载，但未完成密码学验证；清单没有将下载哈希冒称为签名认证。保留上游BSD许可。

上游src/rsn_supp/wpa.h提供可接入的WPA状态机：

| 接口 | 本地驱动所需实现 |
| --- | --- |
| wpa_sm_set_config、set_param、set_own_addr、set_ap_rsn_ie | 传入Lansee真实beacon RSN、本机MAC和实际支持的WPA2-PSK/CCMP策略 |
| wpa_sm_set_assoc_wpa_ie_default | 生成STA关联IE，交给skw_assoc_encode；不能直接复制整个AP安全能力作为协商结果 |
| wpa_sm_notify_assoc | 仅收到目标AP关联成功管理帧后通知 |
| wpa_sm_rx_eapol | 从SDIO数据RX提取本机EAPOL帧；保留来源BSSID、长度和加密标志 |
| wpa_sm_ctx.ether_send | 实现EAPOL帧发送及TX信用/完成处理 |
| wpa_sm_ctx.set_key | 映射SDK ADD_KEY/DEL_KEY、PTK/GTK索引、密钥和重放序号，必须等待固件成功返回 |
| wpa_sm_ctx.deauthenticate | 失败时断开本机STA、关闭数据授权、清除瞬时密钥 |
| set_state(WPA_COMPLETED) | 仍需确认密钥安装和netdev数据路径，然后运行DHCP并验证实际收发 |

待接入主机计时器、可信随机源、上游crypto实现、密钥生命周期以及NuttX Ethernet netdev。不能用固定随机数、跳过MIC检查、伪造成功状态或仅填一个IP代替联网。
Wi-Fi密码保持在本地私密目录，没有包含在此源代码、上游源码、VM或日志中。

## 下一次板端步骤

恢复COM11后先只读确认系统状态，保留蓝牙配对/加密证据。新候选将共享现有唯一SDIO RX线程，在独立状态锁和有界超时下接入这些命令。协议版本、AP安全策略、ACK序号、认证/关联响应都需要验证；失败时清理本机STA。
完成EAPOL与密钥安装、netdev、DHCP之后，才能报告Lansee联网；之后验证蓝牙实际GATT数据服务和双无线连接共存。

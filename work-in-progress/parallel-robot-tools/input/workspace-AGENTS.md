# VelaVision 工作区入口

用户已要求将旧开发、当前无线适配、前端和 AI 日志统一在一个源码仓库。

- 当前主项目是 `E:\openvela\VelaVision`。先读其 `README.md`、`project-manifest.json` 和 `docs/代码日志对应表.md`。
- 主项目 Git 分支为 `dev-ai-contest-2026`，远程来源为用户提供的 allenxun fork；本地整理尚未提交或推送。
- 源码在主项目 `app/`、`board/`、`port/`，配套在 `host/`、`mcu/`、`frontend/`；旧 PC 程序在 `legacy/`，未完成无线组件在 `work-in-progress/`。
- AI 日志必须在同仓 `VelaVision/logs/maomaojiang01/`。更新两个显式项目主会话后运行原版官方校验器；真实范围、脱敏和未完成采集项必须保留。
- Ubuntu `/home/swl/openvela` 是 SDK/编译工作区，项目源码副本为 `/home/swl/openvela/work/velavision-project`。用主项目 `tools/sync_sdk.py` 核对再同步，不能静默覆盖未知 SDK 改动。
- 阶段目录和旧 candidate 是证据归档，不再作为独立产品开发入口。新工作在统一项目中进行并更新代码、构建、日志对应记录。
- 最新无线真机：`wifi-amsdu-index-20260909` 当前在 RAM 运行，Lansee WPA2、DHCP（10.3.0.214）、首次网关 40/40、真实 A-MSDU 1 组 2 子帧交付通过。源码与构建哈希见 `evidence/build/wifi-amsdu-index-20260909/verification.json`，实测见 `evidence/wifi-amsdu-index-20260909/` 和 `docs/WiFi聚合帧接收修复_20260909.md`。手机已重新加密连接；约 50 秒保持期间网关 Ping 50/50、无新增断开。当前 Wi-Fi/手机 BLE 均连接，COM8 无持续观察进程。并发证据和边界以最新 device-state.json 为准。`wifi-amsdu-diag` 仅编译未上板。旧 `wifi-ip-rx` 曾 40/30 丢包，不能沿用旧“尚未恢复 Wi-Fi”状态。前端仍 receive_credentials:true/connect:false；正式 connect、长期运行/完整重密钥、DNS/互联网待做。
- 最新 30 分钟长测：`evidence/stability-20260909/wifi-run-01/`，1800.11 秒、1500 发/1499 收，Wi-Fi 全程在线、空闲堆稳定，严格零丢包标准未通过。手机计时前断开且未恢复，蓝牙长连接未验收；当前手机 BLE 未连接、Wi-Fi 在线，COM8 无测试进程。以此覆盖上一条历史短时连接快照。Agent 未部署，模型服务尚未选定；接续 `docs/Agent部署接续_20260909.md`。
- 本轮不启动云台，不刷 eMMC/STM32，不重复旧硬件测试；硬件操作按用户后续实际任务和既有授权判断。源码/日志整理不代表远程提交授权。

- 2026-09-09 最新覆盖：手机确认 10 次重连每轮收到列表和 scan_done；`reconnect-scan-run-01/acceptance.json` 为合并验收，保留原自动结果。共存保持 1800.11 秒、1497/1500，BLE 连接保持分项通过，零丢包未通过。之后恢复 Wi-Fi 出现 ARP/网关不可达，19:54 原固件复查 5/5；同次发现 BLE reason 8 超时，用户确认一直在附近且 App 前台，原因未知，不能宣称正式稳定通过。19:55 快照 Wi-Fi 在线、BLE 未连接，COM8 无持续进程。详见 `frontend/无线稳定性与重连实测_20260909.md`。正式前端 connect:false、真实状态/联网事件尚未接入，Agent 未部署。

- 19:59 用户报告重连后，快照 connections=14/disconnections=14/reason=19，BLE 已断开；60 秒保持未满足开始条件，仅被动采集。需要对照 App 日志，不能断言用户主动退出。证据 `recovery-ble-attempt-result.json`。

- 20:17 最新覆盖：ble-connect-20260909 已 RAM 启动，SHA256 73c73e2c60165a0e0f19ab760625d3ed8a7dad24eecf61693e9551428f3ff0f3。真实 Windows BLE → 指定 SSID/密码 → WPA2/DHCP → wifi_connected/IP/status 已验证，connect:true；Android/iOS 待前端验证。首轮网关4/5、首包sendto101未解决。已主动断开 Wi-Fi 允许 X 扫描，蓝牙服务注册且测试客户端已主动断开。新版本长期保持未重测，旧结论保留原版本。见 `frontend/真实联网联调说明_20260909.md`；无刷写/云台/远程提交。

- 构建追溯修正：ble-connect 实际 RAM 加载哈希为 1ed2ebc7516acf0c1a81bfaa409a537fa97380154066d305dbc9585f7802c28d（ramload-progress.txt），本地重复构建哈希 73c73e2c60165a0e0f19ab760625d3ed8a7dad24eecf61693e9551428f3ff0f3 不能冒充已加载镜像。已增加完成产物不可覆盖保护。新 wifi-arp-20260909 独立编译中；当前 COM8 可打开但状态命令和换行均无回应，运行状态未确认，等待用户核对供电/串口。

- wifi-arp-20260909 已独立编译通过（ARP等待250ms/5次、ARP计数、PROV最近结果），协议/桥接测试及12项前端测试通过；尚未上板，COM8无回应需先核对环境。新前端scan()在线时明确拒绝且旧扫描页不自动断开BLE。后续见 `docs/WiFi完善与ARP等待调整_20260909.md`，不能复用旧版本实测结论。

- 2026-09-10 最新：wifi-arp-20260909 已 RAM 上板；Windows BLE 真配网、WPA2/DHCP、真实 IP 回包通过，IP 10.3.0.214。空 ARP 缓存起步网关 5/5（含首包），BLE/Wi-Fi 60 秒保持通过。测试客户端已主动断开，Wi-Fi 保持在线。仅本轮有限验证，非长期稳定或互联网验收。见 docs/WiFi上电复验_20260910.md。 固件实际加载 SHA256 9dc19c97c2d2aa5f49bc3bca36d04f026c25c096ec3894605ba7ac4d7dc4ce5d。冷上电原为9月4日基础固件，RAM无线版本不会断电保留。

- 2026-09-10 资源接入当前状态：已完成64位DDR审计工具及8项测试，实测eMMC为29.1GiB；U-Boot执行只读mmc part后无回应，Wi-Fi/BLE未恢复，等待断电重上电。未写eMMC、未启用DDR扩容。见docs/DDR与eMMC资源接入_20260910.md。 下一步先恢复板端，不再重复mmc part；旧Wi-Fi在线快照已失效。

- 2026-09-10 10:03恢复完成：用户重新上电后已重载wifi-arp-20260909，实际镜像哈希9dc19c97c2d2aa5f49bc3bca36d04f026c25c096ec3894605ba7ac4d7dc4ce5d；Windows BLE真配网回IP10.3.0.214，网关5/5。客户端主动断开，Wi-Fi在线、BLE服务保留。没有重复mmc part，没有写eMMC，DDR扩展尚未启用。证据evidence/resource-recovery-20260910/。

- 2026-09-10：model-arena-20260910独立编译/链接通过，新增显式1GiB CPU模型池和k7mem稀疏测试入口，未上板。原系统堆/DMA范围未扩展；CPU仍单核，八核规划见docs/八核CPU接入与任务分配_20260910.md。代码/构建见docs/独立DDR模型内存池_20260910.md；当前无线固件未替换。


2026-09-10最新：model-arena-20260910已RAM上板；专用1GiB模型池创建成功，384MiB分配/98304页两轮稀疏读写/释放恢复通过。BLE真配网IP10.3.0.214、网关5/5、30秒保持通过；客户端主动断开，Wi-Fi在线。系统堆仍原范围、CPU仍单核，eMMC未写。见docs/独立DDR模型内存池_20260910.md与evidence/model-arena-20260910/。

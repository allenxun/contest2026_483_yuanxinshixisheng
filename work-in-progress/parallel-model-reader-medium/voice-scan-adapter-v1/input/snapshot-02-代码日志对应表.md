# 代码、日志与验证对应表

2026-09-10 双核主任务：app/k7smp、K7实验SMP配置/CPU映射、公共PSCI启动错误传播已独立编译；smp-diag-20260910真机两A53固定核各10000采样、零错位、共享计数20000、定时休眠通过。第一次编译缺IPI声明、第二次沿用旧Kconfig，日志均保留。随后因最小配置漏BOARDCTL_RESET不能reboot，NSH仍响应；恢复加载一次COM8占用拒绝，无镜像数据写入。smp-reset-20260910已编译，链接cmd_reboot/psci_sys_reset/up_systemreset并通过镜像校验，尚未上板。详见 evidence/smp-diag-20260910 与 evidence/build/smp-reset-20260910。没有将双核诊断记为外设SMP或八核验收；当前等待RESET恢复无线。

2026-09-10 最新验收：`emmc-vfs-20260910` RAM镜像 SHA256 `06320f4b86326ea91d682fb6192dad5c64f7893279f9d73ed57490f80b9fe10b`，只读VFS连续64KiB和跨扇区4字节读取均返回0；GPT/16节点及块接口检查通过。BLE真配网IP10.3.0.214、网关5/5、30秒保持通过，客户端主动断开，Wi-Fi在线。证据 `evidence/emmc-vfs-20260910/device-state.json`。没有写盘或挂载文件系统，非完整模型文件读取验收。

2026-09-10 eMMC块设备：emmc-block-20260910真机注册16节点，geometry/拒写/边界/分区地址转换通过；BLE配网、5/5网关与30秒保持通过。普通dd打开返回ENXIO，SDK源码确认缺CONFIG_BCH。独立emmc-vfs-20260910仅增加BCH与BCH_DEVICE_READONLY，SDK差异审计及编译校验通过，正在RAM加载。对应evidence/emmc-block-20260910、evidence/build/emmc-vfs-20260910；未写盘、未挂载文件系统。

2026-09-10 日志写入修正：`tools/log_daily.py` 跳过内容不变的历史文件，采集进程已重启加载；`tools/test_log_daily.py` 验证跨日追加不改变旧文件和旧目录修改时间。实际刷新核对及官方校验结果见 `evidence/log-unchanged-write-verification.json`。

2026-09-10 原生 eMMC 真机：`emmc-readonly-20260910` 初始化及两扇区重复读取通过；BLE真配网/网关5/5/30秒保持回归通过。证据 `evidence/emmc-readonly-20260910/`，对应构建哈希 fd1462a94c3fad9692cbdd6e3d9fe3bbfb4f4920220eb12997b1a22a201881fe。GPT解析增量正在独立 emmc-gpt-20260910 构建，不能复用前一镜像的实测结论。没有写盘。次会话已接续 parallel-wifi-service 候选，中央日志仍由本会话统一核对。

2026-09-10 VoiceLink 交接接收：主会话核对候选 17 个交付文件和 14 个输入哈希、锁定头文件及已通过测试报告，见 `evidence/voicelink-handoff-20260910/verification.json`。未应用补丁或上板。并行主会话 01a0892e-2964-7ec3-bd76-9ab4937980cb 已显式入日志源，首次 95 条；统一官方校验通过。接口差异及接入顺序见 `docs/VoiceLink交接接收与集成顺序_20260910.md`。

2026-09-10 eMMC 固件接入：核心源码迁入 `app/k7emmc/`，新增初始化状态机、低速平台配置、复位和受限命令接口；四套主机测试通过。`emmc-readonly-20260910` 独立编译、链接与镜像范围校验通过，正在 RAM 加载，尚未声明真机读取成功。构建见 `evidence/build/emmc-readonly-20260910/verification.json`，说明见 `docs/eMMC原生只读接入_20260910.md`。本主会话日志归属 maomaojiang01；VoiceLink 并行目录未改动。

2026-09-10 eMMC 命令层增量：新增 `work-in-progress/emmc-readonly/sdhci_command.{c,h}` 和模拟控制器测试，补 CMD17、R1 检查、地址边界、共享截止时间与失败恢复门禁。`tools/test_emmc_readonly.py` 同时执行接收层和命令层测试，证据见 `evidence/emmc-source-review-20260910/host-command-test.json`。未操作硬件、未构建固件；卡初始化和平台接管仍待实现。本主会话日志统一在 logs/maomaojiang01，未修改并行 VoiceLink 工作目录。

2026-09-10 eMMC 增量：`work-in-progress/emmc-readonly/` 新增有界单块 PIO 接收核心和主机故障注入测试；`tools/test_emmc_readonly.py` 严格编译并运行通过，源码哈希/命令/结果见 `evidence/emmc-source-review-20260910/host-test.json`。仅主机测试，未集成 SDK、未构建或加载新固件。官方 SDK 四个参考 blob 的校验与静态发现见同目录 manifest.json 和源码审查.md。对应本主会话真实 AI 日志，统一归属 logs/maomaojiang01。用户已另开 VoiceLink 会话；本轮未改其暂存目录。

2026-09-10最新：model-arena-20260910已RAM上板；专用1GiB模型池创建成功，384MiB分配/98304页两轮稀疏读写/释放恢复通过。BLE真配网IP10.3.0.214、网关5/5、30秒保持通过；客户端主动断开，Wi-Fi在线。系统堆仍原范围、CPU仍单核，eMMC未写。见docs/独立DDR模型内存池_20260910.md与evidence/model-arena-20260910/。

2026-09-10：model-arena-20260910独立编译/链接通过，新增显式1GiB CPU模型池和k7mem稀疏测试入口，未上板。原系统堆/DMA范围未扩展；CPU仍单核，八核规划见docs/八核CPU接入与任务分配_20260910.md。代码/构建见docs/独立DDR模型内存池_20260910.md；当前无线固件未替换。

2026-09-10 10:03恢复完成：用户重新上电后已重载wifi-arp-20260909，实际镜像哈希9dc19c97c2d2aa5f49bc3bca36d04f026c25c096ec3894605ba7ac4d7dc4ce5d；Windows BLE真配网回IP10.3.0.214，网关5/5。客户端主动断开，Wi-Fi在线、BLE服务保留。没有重复mmc part，没有写eMMC，DDR扩展尚未启用。证据evidence/resource-recovery-20260910/。

2026-09-10 资源接入当前状态：已完成64位DDR审计工具及8项测试，实测eMMC为29.1GiB；U-Boot执行只读mmc part后无回应，Wi-Fi/BLE未恢复，等待断电重上电。未写eMMC、未启用DDR扩容。见docs/DDR与eMMC资源接入_20260910.md。

2026-09-10 最新：wifi-arp-20260909 已 RAM 上板；Windows BLE 真配网、WPA2/DHCP、真实 IP 回包通过，IP 10.3.0.214。空 ARP 缓存起步网关 5/5（含首包），BLE/Wi-Fi 60 秒保持通过。测试客户端已主动断开，Wi-Fi 保持在线。仅本轮有限验证，非长期稳定或互联网验收。见 docs/WiFi上电复验_20260910.md。

Wi-Fi 完善增量：ARP 等待 20→250 ms、ARP 收发计数、最近 PROV 请求结果；新固件 `wifi-arp-20260909` 编译和协议/桥接测试通过。前端在线扫描保护及 12 项测试通过。COM8 无回应，新固件尚未上板；见 `docs/WiFi完善与ARP等待调整_20260909.md`（统一源码入口根目录下）。

20:17 BLE 真配网已 RAM 启动并验证：`ble-connect-20260909`，connect:true；Windows BLE 请求 id 9101 完成原生 WPA2/DHCP 并回真实 IP，status 一致；网关首轮4/5仍有首包ARP问题。源码/协议/桥接/前端测试见 `evidence/build/ble-connect-20260909/`；真机与当前可扫描状态见 `evidence/ble-connect-20260909/`。同一主会话日志，未远程提交。

新增 BLE connect 接入：`prov_wifi.inc`、动态 SSID 选择、真实 status、前端 connectWifi()；协议/桥接内存检查测试、11 项前端测试及固件编译通过。新固件 ble-connect-20260909 正在 RAM 加载，尚无端到端真机通过结论。构建见 `evidence/build/ble-connect-20260909/`，对应当前主会话日志。

2026-09-09 本轮验收收尾：手机确认 10 次重连每轮收到列表和 scan_done，合并结论在 `evidence/stability-20260909/reconnect-scan-run-01/acceptance.json`，原观察器结果保留。30 分钟共存 1497/1500，零丢包未通过；随后 Wi-Fi 恢复阶段出现 ARP/网关失败，19:54 复查 5/5，同时发现 BLE reason 8 超时，用户确认 App 前台且在附近。两项后测异常在 `post-test-anomalies.json`，无已确认根因或固件修复。新增只读/有界 `tools/probe_wifi_gateway.py`；未重启、未刷写。日志归属本主会话和 `logs/maomaojiang01/`。
19:36:59 共存长测完成：1800.11 秒、1497/1500；BLE/Wi-Fi 连接保持通过，严格零丢包未通过。随后主动退出 Wi-Fi 开始独立 X 扫描/10 次手机重连采集，尚未验收。观察器新增 NSH 提示符处理，合成测试共 8 项通过；无固件修改。证据及结果见 `evidence/stability-20260909/`。

19:06:59 启动手机 BLE＋Wi-Fi 共存保持测试，证据 `evidence/stability-20260909/coexist-run-01/`；尚未完成，不计作通过。新增 `tools/observe_ble_reconnect.py` 及 7 个合成观察器测试，仅准备后续手机重连采集。`tools/summarize_wireless_stability.py` 增加独立 BLE/Wi-Fi 保持结论，严格综合零丢包标准保留。详见 `docs/蓝牙共存与重连验收_20260909.md`，对应当前主会话；无固件修改。

2026-09-09 官方赛道对齐：新增 `docs/官方硬件赛道对齐与目标_20260909.md`，核对官方 K7 待适配状态、代码交付与 Agent 定位，修正 README/目标文档中的旧无线状态。本轮无固件改动或新增真机验收；对应当前主会话。累计日志以同仓 manifest 为准，下方数量保留为历史快照。

最新长测：`tools/run_wireless_stability.py` 与 `tools/summarize_wireless_stability.py` 对应 `evidence/stability-20260909/wifi-run-01/`。1,800.11 秒，1,500 发/1,499 收，Wi-Fi 保持在线；严格零丢包未通过，手机 BLE 未连接，不能计作蓝牙长稳通过。本轮无线固件未变；Agent 仅完成部署条件核对和配置模板，未上板。日志仍归属本会话和 `logs/maomaojiang01/`。

日志持续采集修正：当前主会话长轮次不会触发 Stop，新增 `tools/watch_project_logs.py` 每 30 秒按源文件变化刷新当前会话，延续按日分文件、连续 seq 和脱敏策略。运行信息及最新官方校验在 `private/log-collector/watcher-status.json`；此变更不涉及固件或硬件。

旧主会话分日更新：`01a06679-4033-7993-b989-6269e03e0e70` 的 7,167 条记录也已按北京时间拆分到真实事件日期目录。按日期重新拼接的 SHA-256 与拆分前完全一致，序号 0–7166 连续；详见 `evidence/old-session-daily-split.json`。原版官方校验通过，后续手动刷新沿用分日规则。

最新 `wifi-amsdu-index-20260909`：首次网关 40/40、实际 A-MSDU 1 组 2 子帧交付通过，Lansee WPA2/DHCP 成功；证据 `evidence/wifi-amsdu-index-20260909/`，源码、软件测试和构建对应 `evidence/build/wifi-amsdu-index-20260909/verification.json`。当前主会话日志仍归属 `logs/maomaojiang01/`。手机 BLE 保持加密连接期间网关 50/50、无新增断开也已记录；正式前端 connect、小时级稳定性与 BLE 业务并发吞吐未验收。下方保留历史。

日志目录规则更新（2026-09-09）：当前开发主会话 `01a07ed4-3f0d-7450-8bb1-bb756849cb4e` 已按北京时间分日，9 月 9 日事件在 `logs/maomaojiang01/2026-09-09/codex__01a07ed4-3f0d-7450-8bb1-bb756849cb4e.jsonl`。9 月 8 日事件仍保留原目录；跨日 seq 连续，manifest 合并累计。手动导出和自动 hook 共用 `tools/log_daily.py`，原版官方校验通过。

2026-09-09 最新无线进展：原生 Lansee WPA2 四次握手通过，证据 `evidence/wifi-auth-20260909/lansee-auth-01.jsonl`；运行固件及源码对应 `evidence/build/wifi-auth-20260909/verification.json`。IP/DHCP 为后续独立开发，不计作联网通过。对应当前主会话，日志归属不变。详见 [认证与 IP 接入](WiFi认证与IP接入_20260909.md)。

最新修正：`phone-rpa-20260909` 针对手机重新配对 0x04，分离连接时随机地址与身份地址；实际地址选择函数回归测试和独立编译通过，正在 RAM 加载。见 [手机重复配对地址修正](手机重复配对地址修正_20260909.md) 与 `evidence/build/phone-rpa-20260909/verification.json`。对应当前主会话；首次手机连接成功不等于反复配对和稳定性验收通过。

手机业务联调补充：用户确认连接稳定，要求继续“X → 真实扫描列表 → 提交 Wi-Fi 信息 → 已收到回执”，不要求联网。当前镜像已有此协议，本轮未更改固件；新增 `frontend/手机调试器操作卡.md`、`手机调试HEX分包.txt` 及仅含测试密码的生成脚本，更新操作包。现场业务收发仍需手机开启 Notify 并发送命令，不能把资料生成当作手机收发通过。

手机配对修正 `phone-pairing-20260909`：统一配置、`port/tracked/nuttx/wireless/bluetooth/bt_keys.c`、`Kconfig` 和 `app/k7radio/skw_bt.c`；对应当前主会话。实际分配器测试及独立固件编译通过，证据 `evidence/build/phone-pairing-20260909/verification.json`。记录回收与现场排查说明见 [手机蓝牙断连排查](手机蓝牙断连排查_20260909.md)，手机连接验收仍以新镜像现场记录为准。

2026-09-09 手机联调新增：[手机蓝牙断连排查](手机蓝牙断连排查_20260909.md)。仅修改只读串口观察工具，新增手机 SMP 0x09 / 断开 0x13 现场证据；固件未变，Android 长连接尚未通过。对应当前主会话与同仓 `logs/maomaojiang01/`。

最新范围：用户要求先完成信息接收、不要求联网。`credentials-20260909` 已编译、RAM 启动和真机验证真实扫描/接收回执；证据在 `evidence/credentials-20260909/`，对应当前主会话。源码、测试和前端说明见 [本轮开发记录](配网信息接收开发_20260909.md)，下方为历史快照。

最新无线增量见 [Wi-Fi EAPOL 接收进展](WiFi-EAPOL接收进展_20260909.md)：对应当前主会话，源码/固件哈希与测试输出位于 `evidence/build/eapol-rx-20260909/verification.json`。下方首次统一版本源码清单和 80 项一致性为历史快照，不代表本轮改动后的再次验收。
统一仓库：`E:\openvela\VelaVision`；日志归属：`logs/maomaojiang01/`。

2026-09-09 日志采集配置更新：新增 `tools/auto_collect_logs.py`、`tools/install_log_hook.py` 和范围测试；对应真实会话 `01a08456-0276-7772-b214-0a86086f5974`。已刷新两个历史主会话并合并第三会话；下方数字为此前集成快照，最新数量/哈希在同仓日志 manifest。自动入口已安装、直接调用验证通过，已信任启用且 Codex CLI 自动触发验收通过；已打开的桌面任务需重新加载，详见 [自动日志采集](自动日志采集.md)。本次不改变固件或硬件验证结论。
## 日志覆盖
- 旧主会话：7167 条，2026-09-03T08:53:37.460Z 至 2026-09-08T02:21:45.985Z。
- 当前主会话：3569 条，2026-09-08T02:23:54.126Z 至 2026-09-09T04:09:14.478Z。
- 两个会话各自 seq 从 0 连续递增，不串改日期或把两个会话改成一个会话。
- 当前快照不含导出之后的新增消息；运行更新脚本可刷新。未重复合并子任务继承历史，未恢复内部推理。

## 代码到日志索引
下表是对真实日志中的路径/名称引用检索，不是补造逐次 Git 提交或宣称每条引用都代表代码修改。详细锚点在 `evidence/code-log-map.json`。
| 模块 | 源码位置 | 旧会话引用数 | 当前会话引用数 |
| --- | --- | ---: | ---: |
| BSP / USB / 平台 | `board/kickpi_k7; port/new/nuttx; port/tracked/nuttx` | 367 | 142 |
| 人脸 / 姿态 / 三视角拍照 | `app/k7host; host/vision` | 709 | 47 |
| 云台 / STM32 | `app/gimbal; mcu/stm32-v1.3` | 545 | 91 |
| NPU | `app/k7npu` | 141 | 82 |
| Wi-Fi / BLE / 前端 | `app/k7radio; frontend; work-in-progress/wifi-link` | 0 | 523 |
| 旧 PC / 仪器模型 | `legacy/pc-delivery` | 201 | 31 |
| 统一构建 / 日志 | `tools; logs/maomaojiang01` | 23 | 54 |

## 版本与验证证据
- `evidence/source-files.json`：本仓源码/模型/脚本的逐文件 SHA-256，识别当前实际代码。
- `evidence/sdk-inventory.json`：来自 VM 的文件路径、SDK Git 基线及最初取回哈希。
- `evidence/accepted-source-comparison.json`：80 项旧验收源码与统一目录全部一致。
- `evidence/build/integrated-build.json`：同一 ELF 中四个应用入口、配置和固件哈希；仅编译验证。
- `evidence/log-snapshots.json`：两个原始会话快照哈希/截止时间、事件数量、脱敏与排除项。
- 每条 JSONL 的 `metadata.source_line` 与 `source_record_sha256`：定位原始会话记录；`seq` 定位交付日志。
- `evidence/official-log-validation.json` 与 `.txt`：未修改官方校验器的实际运行结果。

历史没有逐次提交，不能证明不存在的 commit 对应。今后从此统一仓库产生代码提交，并同步同仓日志和版本清单。文件/格式核对通过，不代替联合硬件验收。

2026-09-10 VoiceLink 接入核对：外部语音目录源码只读评审，5组核心/解析主机测试重新编译执行通过；板端音频、sherpa/ONNX Runtime、共享Wi-Fi接口与内存规划待做。未修改运行固件；见 docs/VoiceLink接入评估_20260910.md、evidence/voicelink-review-20260910/review.json。归属当前主会话日志。

2026-09-10 用户确认4GB DDR/32GB eMMC：核对当前126MiB映射、DTB/固件保留区及未启用MMCSD，形成docs/DDR与eMMC资源接入_20260910.md。只读评估，未改写运行固件或存储，归属当前主会话日志。

2026-09-10 SMP增量：app/k7smp、ARM64 CPU启动返回值及RK3576 MPIDR映射、独立2/4/5/8核配置均有独立构建和真机证据。八核最终证据见 evidence/smp-eight-20260910/cpu-acceptance.json；三次主机串口参数错误和首版缺reboot均保留。不将单核无线或主机语音结果计算为八核外设验收。归属当前主会话，日志须刷新后以manifest与官方校验为准。


2026-09-10后续实测：smp-service-20260910 已RAM上板。8核诊断通过，系统/无线线程亲和性0x1已核对；BLE真实配网及60秒保持、BLE加密连接期间Wi-Fi网关5/5、本轮拒收0。当前保留此候选运行，测试客户端主动断开。不是持续计算并发、外设全量或长稳验收；k7_provision栈峰值6688/8112字节，后续共享语音服务接入前应复核余量。见 evidence/smp-service-20260910/acceptance.json。


实际增量：smp-load-20260910 RAM运行，四A72各60秒、1412766批零计算错误，ping45/45；时间重叠核对BLE回包11次、网关回复45次。A-MSDU快照2→5，不满足严格零接收异常，不能归因为计算负载或宣布长稳。首轮后台提示符采集失败未启动计算；第二轮修正主机采集后一次完成，全部记录保留。详见 evidence/smp-load-20260910/acceptance.json。


2026-09-10 原生Agent基础增量：app/k7cxx、K7异常表及首构造注册修复，经cxx-unwind独立构建/ELF检查与真机探针通过；无线真配网/BLE30秒/网关5/5。第一轮TLS_TASK缺失编译失败、第二轮异常表缺失取消加载及无线恢复失败均保留。app/k7agent/model_reader与app/k7neon为已迁入待验收候选，模型与Agent未部署。证据evidence/cxx-unwind-20260910/acceptance.json；日志归属当前主会话，子代理独立记录未宣称完整单独入库。

2026-09-10后续：neon-file64串口中断后恢复，实际off_t64、CPU4/5 NEON短时、BLE配网/IP/30秒和网关5/5通过，A-MSDU拒收1仍保留。另独立cxx-locale运行库构建及真实llama39个ARM64对象、链接/异常表门禁通过，未上板或加载模型。新增三代理第二轮候选48文件哈希已核对，宿主结果不替代设备验收。完整过程和命令见docs/原生llama编译与NEON验收_20260910.md；tools/check_llama_native_compile.py、check_llama_native_link.py、record_neon_acceptance.py对应当前主会话，同仓日志须以最新manifest/官方校验为准。


2026-09-10追加：新增app/k7eh与app/k7ehcontrol保存冷并发异常失败和独立对照；app/k7graph真实2/4线程零权重图与无线回归通过；app/k7agent/tool_api仅目标编译通过。链接v1拼错符号门禁已在v2纠正，原失败/错误记录保留。tools/observe_graph_core.py、observe_eh_control.py、record_graph_acceptance.py对应本主会话，最终日志须重新官方校验。


2026-09-10：app/k7arena经独立构建、实际TU宏/ELF检查和RAM真机通过32KiB/8192项set-get及释放；配套无线30秒、网关5/5通过。证据evidence/arena-provider-20260910/acceptance.json。USB只读MSC、FAT与模型同句柄读取仍是候选，不宣称已枚举U盘或加载权重。来源为当前主会话及候选交接哈希；官方日志须刷新后核对。


本轮真实结果：USB新节点/dev/sda，512字节扇区、60555264扇区，两次LBA0 CRC32=b1241e76且关闭成功；未挂载/未写盘。无线恢复30秒及网关5/5，拒绝1→1保留。VID/PID未输出，严格身份绑定验收尚未满足。见evidence/usb-readonly-20260910/runtime-acceptance.json；当前无持续串口进程。

2026-09-10 用户明确近期顺序为本地语音配网后再接小米云API。app/voicelink迁入6份冻结核心/解析器，增加异步扫描事务、取消/超时、64项上限，并修复连接失败返回选网与可恢复扫描失败后重新唤醒。正式源码O0/O2各14场景通过；全部音频/网络端口为模拟，未接入固件。结果与50份并行音频/扫描交付哈希见evidence/voicelink-core-integration-20260910/stage.json。tools/integrate_voicelink_core.py、test_voicelink_flow.py、record_voice_provisioning_stage.py归属当前主会话；子代理交接不代表独立完整日志已自动采集。此前FAT已编译通过的pending状态同步纠正，未RAM加载。完整待做项见docs/本地语音配网优先实施_20260910.md。


2026-09-10：audio-preflight独立构建及实际ARM64编译单元/ELF/raw校验通过，RAM上板完成8个固定CRU/IOC地址两份快照，无寄存器写、I2C事务或录放音。无线同镜像真实IP、BLE30秒/网关5/5，接收拒绝0→0。证据evidence/audio-preflight-20260910/runtime-acceptance.json；app/k7audio和配套tools归属本主会话，日志按最新manifest/官方校验为准。

2026-09-10 板载音频最高优先级：app/k7audiohw已在audio-io-b镜像真机通过固定codec双次读取与STOP/恢复；app/k7sound集成codec v2/SAI PIO v2与PMU/clock/pinmux，独立编译已通过，录放音实测待完成。CRLF脚本失败和复用构建目录未发现新Kconfig的失败均保留；未加载未通过版本。Windows BLE同版本两次DeviceNotFound，不能宣称无线恢复。所有真实结论绑定各自evidence与artifact，未刷写/云台/远程提交。


2026-09-10 18:42真实音频首轮：audio-sound镜像SHA256 58e5c5ce5a6ffc8b116c75f874ef430f23a7a0192f819ab146484e02b2cf2313已RAM启动，SAI23073576、codec初始化及停止/恢复成功。tone预填充和capture首帧后均返回-71，未取得完整录放音；四字段FIFO求和修正在独立audio-fifo版本准备。原始结果见evidence/audio-sound-20260910/first-attempt.json，失败未覆盖。


2026-09-10 18:54：audio-fifo镜像 741c9b2f8b23f6f247da865201061343cbe36b924404457f82f1d6630ce14020 真机FIFO首读00104104，四字段总16，3200帧短音传输0，用户确认三声可听到；48000帧/3秒采集也返回0但全部为零，录音未通过。数据和用户确认分别保存在evidence/audio-fifo-20260910/runtime-results.json，零样本原始WAV在zero-capture/。下一audio-normal对照只改codec正常功耗并加启动前诊断；可选原始PCM缓冲回放只由显式replay启用，未实测。


2026-09-10 19:05 audio-normal实测：正常功耗寄存器读回成功，但3200帧仍全零；0f=20只比写30少未定义bit4，mute位已清，不判静音。SDI0下拉、PATH=e4e4、GPIO有限采样全低。进一步从精确官方clk-out.c确认独立IOC26046400 bit1主时钟输出门控遗漏，audio-mic补齐该门控与官方pull_none、20ms只读引脚观察，并加入独立reset的ADC对照模式；合并平台两组O0/O2测试、ARM64编译/ELF通过，RAM加载中。见各版本evidence，未宣称麦克风成功。


2026-09-10 audio-mic 已RAM上板，外部MCLK门控从1f变1d；首次捕获真实变化数据，用户配合的48000对原始录音已保存 voice-first。尚未验收：严格每4帧只有phase0非零，其余3帧全零，不能按16k正常录音交付或简单删零。ARM64机器码/编解码器模式审查未发现相应步长或模式错误；独立audio-rxtrace仅加前32次FIFO读前/读后记录，ARM64/ELF通过，当前RAM加载。真实材料见 evidence/audio-mic-20260910/runtime-results.json 与 evidence/audio-rxtrace-20260910/。无线未启动，未写eMMC。


2026-09-10 audio-rxtrace真实3200对采样200040us，前32字证明FIFO0/1/2/3依次每62.5us各提供两字，非空读造成插零，MONO=0。新audio-reset独立镜像已编译/ELF核对，包含互斥capture-clear、capture-reset、capture-clockwait三入口及原始trace；ARM64/主机通过不代表实机修好。RAM加载中；串口恢复只读确认U-Boot，未刷写。默认capture仍保留原路径。


2026-09-10 20:07实际：audio-reset已RAM启动。CLK/FS关闭时start-clear超时并锁住；同镜像RAM重载恢复。H/M复位与20us时钟等待均执行成功但每4帧3零未消失。MIC采集48000对后由板载喇叭原样回放，两端传输/停止返回0，用户明确没有听到声音；随后同版本三次短音用户全部听到。不能验收语音回放。原始PCM及实听结果见evidence/audio-reset-20260910/runtime-results.json；无线未启动，无eMMC写入。下一版仅准备可控DAC音量档位，默认与原始PCM保持不变。


2026-09-10 最大音量测试：用户要求最大音量；app/k7sound增加预备态DAC档位及replay-max/tone-max，合法最大DAC00/OUT2 21，先关闭功放并逐项读回，失败不激活。候选O0/O2模拟检查、正式ARM64构建、ELF及raw一致性通过；image 0a68990a8b36f3e38154959a5ed33f209d0bf5a6c6a825f36ae2c06959246f9f，RAM加载中，未宣称实听成功。原始PCM/PIO不改，见evidence/audio-gain-20260910/integration.json和docs/板载录音回放操作_20260910.md。


2026-09-10 20:22实听确认：audio-gain录48000对并replay-max两次，DAC1a/1b=00、OUT2 30/31=21均真实读回，搬运与停止0。用户回复“听的清楚但是有一些杂声”，证明板载MIC录音→板载喇叭人声回放基础功能已打通；不等同纯净音质/正确16k格式验收，周期性零采样仍在。20:23同段低输出音量对照已执行，等待实听反馈。证据evidence/audio-gain-20260910/runtime-results.json与voice-max-first原始WAV。


用户后续纠正：最大音量有杂音，而且要仔细听才能听清说什么。以上基础回放确认只证明可听/可辨认，不代表清晰可用；音质验收仍未通过。下一步分开做输入PGA增益与SAI接收请求对照。


后续输入增益对照：audio-input-20260910已独立编译/ELF及raw一致性通过，RAM加载中。只新增capture-pga24（ADC09=88、+24dB）与启动前SAI槽掩码只读快照；默认capture与PIO保持不变，RDE候选未集成/未启用，DMA硬件前置状态尚未证明。参考audio-input-root候选O0/O2寄存器差分与失败检查。旧audio-gain音频回放可辨认但用户需仔细听、杂声未解决。

2026-09-10夜间：用户授权持续至9月11日09:00，无需人工确认。audio-input最终反馈为“人声更大，但杂声仍明显”。audio-filter候选冻结哈希核对后迁入app/k7sound，新增逐声道独立输出滤波，不删除或归一化原PCM。正式ARM64/ELF/raw通过，RAM镜像8c8f46b4a354be34e6ff8d3d430cb81f70d583a8a0f929aeed0047ae5f1585fc，200ms采集及一次MA4回放返回0，功放关闭；无人实听，不算音质通过。HP80仅主机通过。真实录音的主机ASR仍有偏差，不算板端语音识别。相同镜像Wi-Fi由私密串口提交认证/DHCP成功，短录音前后网关各5/5；两次Windows BLE操作均DeviceNotFound，失败保留。对应tools/integrate_audio_filter.py、check_audio_filter_host.py、check_audio_filter_asr.py、record_audio_filter_stage.py及record_audio_filter_wireless.py；evidence/audio-filter-20260910保存原始证据。日志刷新与官方校验结果仍以最新报告为准，子代理交付不表示其独立日志完整入库。

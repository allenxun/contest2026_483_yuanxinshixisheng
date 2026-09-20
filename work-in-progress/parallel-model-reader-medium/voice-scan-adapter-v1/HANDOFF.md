# VoiceLink 共享异步扫描候选（主机验证，未集成硬件）

本次具体缺口：正式 app/voicelink 已是 beginScan/pollScan/cancelScan；旧 parallel-wifi-service 适配仍是同步 scan()/IoStatus，且直接调用 broker，不能接当前接口。parallel-wifi-dispatch 已提供共享连接仲裁但无 SCAN；本候选只为它增加共享扫描状态及当前 WifiPort 桥接，逐字复用 C 代理 collector 与扫描快照结构，不建立第二套无线锁或 BLE 表。

## 交付与边界

- wifi_broker.c 完全不变；wifi_broker.h 仅尾部追加 WB_SCAN，原枚举值不变。
- wifi_dispatch.h 增加可选 scan 指针；c 仅 include 和在单 owner pump 中调用 ws_pump。初始化 memset 保持未 attach 的默认路径。结构布局改变，必须所有头/对象同批重编；不能二进制混用旧库。
- wifi_scan.c/h：一个固定结果槽、无 malloc，BLE/VOICE 固定身份，同一 dispatcher 锁分配不可复用 ticket；租约由同一个 pump owner 设置 WB_SCAN。连接 wb_begin 会拒绝非 FREE，无直接读 BLE 全局表。
- voice_wifi_adapter.cpp/hpp：当前 voicelink::SharedWifiPort，构造 (wd_dispatch&,ws_service&,timeout_ms=30000)，poll 不 pump，不执行硬件。dispatcher/scan 必须初始化、彼此绑定并长于适配器生命周期。scan/cancel 用 ws_*，connect 用 wd_*，不直接调用 broker。
- scan_collector.c/h 与 scan_contract.h 是原交付的逐字副本。旧 contract 全局 voice_scan_* 声明仍只是提案；本实现显式 service 参数 ws_voice_*，不要链接调用旧未定义全局声明。
- 无生产假后端、模拟 IP 默认值、SDK 操作或板端 ASR/无线验收。本候选闭合的是共享仲裁代码，不是正式无线 worker 的硬件接线。

## 可执行接入清单

1. 复用 parallel-wifi-dispatch 的原 INTEGRATION，而非直接编译旧 BrokerWifiPort。将这里 broker/dispatch/collector/scan C 对象与新的 SharedWifiPort 加入一次一致构建。服务初始化 wd_init 的 proven_offline 不能猜 true：须确认旧 join/维护任务退出、接口和密钥清理且真实离线；否则维持 EXTERNAL/BUSY。ws_attach 在发布给任何线程前执行，供真实 submit/stop 回调，绝不空实现返回成功。
2. 唯一普通服务线程按请求/事件唤醒并有界定时 wd_pump。ws_pump 是内部实现，客户端不得单独调用。锁应为普通任务可用的短临界区，所有 backend 回调在锁外；submit/stop 必须有界非阻塞。首次扫描在本轮 dequeued 连接处理前获得仲裁，允许扫描优先；不承诺严格 FIFO 或无饥饿。
3. app/k7radio/prov_service.inc PROV_SCAN（冻结约249行）换为 ws_ble_begin，保留独立 epoch/JSON id→ticket 映射、加密订阅/LPWORK 通知门禁。完成后 ws_ble_poll 拷贝 snapshot 再编码列表，禁止使用 g_prov_scanning/g_prov_aps 作服务存储。BLE 断线只丢旧通知映射，不取消 VOICE。单结果槽在下一 begin 时可被替换：旧 snapshot 是值拷贝且不变，旧 ticket 再 poll 会 UNKNOWN；客户应在开始下一轮前消费前轮终态。
4. app/k7radio/k7radio_main.c fw_wifi_scan（1192）只能在专用 worker 内运行，submit 接收成功前复制 ticket。非零 submit 必须证明无 worker/interface 已启动，才能立即释放；已产生任何副作用就必须返回 accepted、经完成事件走 held 清理。fw_wifi_scan 当前单 int 返回不足以表达清理凭据：分离 scan_done、STOP、CLOSE 状态，修补 OPEN 后拿 g_wifi_state 失败直接返回而未 CLOSE 等错误路径。不能简单将 ret==0 填满所有 fence。
5. RX 类型11/fw_wifi_scan_report（732/909）通过实际 skw_bss_decode 将完整字段传 ws_record(service,ticket,&record)，拒绝迟到 ticket；不要用 g_wifi_seen 诊断表。固件报告自身无事务 ticket，本地 ticket 检查不能辨认已残留在 SDIO/RX 队列中的旧帧。必须由 supervisor 证明上一轮 STOP/自然完成、CLOSE 和接收队列排空/回调退出后，才给下一轮绑定 ticket。未证明就 held，不给旧事件贴新 generation。
6. worker 结果及 supervisor 退出证明合成 ws_done：success+scan_done 才有成功列表；stop_ok（自然完成时可代表已证实无需额外 STOP，不能盲填）、close_ok、worker_exited、rx_quiescent、offline 全部真才释放。worker 在 return 前发 done 信号不等于已退出；必须 supervisor join/任务退出证据。每次事件 sequence 严格递增，完整快照，不累计碎片。ws_post 的 FULL 需保留原事件重试，不能丢释放事件。同步 submit 回调内发布事件也只在后续 pump 消费。
7. cancel/timeout 立即给客户终态，但仍 held；stop 回调成功仅表示请求已接收，绝不释放。回调非零每 pump 重试；没有强杀线程或强制释放定时器。任何 STOP/CLOSE/RX 清理失败可永久占用资源，需 supervisor 故障处理，不能超时擅自接管。取消后完整晚到成功仍保持 Cancelled/Timeout，不报 Ready。
8. 同时将 BLE CONNECT、VOICE CONNECT 与全部 wifi-* CLI/auth 旁路纳入 dispatcher，或服务开启时明确拒绝旧入口。现有 prov_wifi_connect 会主动停旧网络，必须停用该绕行；仅将语音路径接入而保留旧 BLE/CLI 直呼并不能保证互斥。不能将 g_wifi_operation 瞬时可锁当在线维护资源已释放。
9. OWNED 在线 scan 返回 Unsupported 且零 submit/stop；QUEUED/RUNNING/DRAINING/EXTERNAL 或另一 scan 返回 Busy。连接成功只沿原 broker 的 authenticated+DHCP+有效非链路本地 IPv4+worker退出+link_up 完整权威结果；PROGRESS、接收密码或关联不升级。旧 broker 对 auth失败等没有精细原因，桥接返回 Failed，不伪造 WrongPassword。密码仅复制到原 dispatcher 队列，caller/backend 各擦自己的副本；不记录凭据。连接成功 lease 持续 OWNED，cancelConnect 不是 disconnect；显式 supervisor wd_voice_release 才开始拥有者断开。

## SSID 和容量

结果最多64，按原 collector BSSID 去重；重复项更强 RSSI 替换完整记录。snapshot 保留原 SSID bytes/BSSID/security。当前 AccessPoint 没有 BSSID/原始展示分离字段：桥接仅按长度原样构造 UTF-8 名称，不截断/标准化/合并；隐藏SSID不列入语音选择，控制字节/非法UTF-8会使该次适配结果 Failed，底层快照仍保留。不能将不可表示的 SSID 改写为另一个可连接名称。open 网络仍由既有 dispatcher 凭据限制拒绝，未扩大认证能力。

## 真实主机验证

运行：C:/Users/pc2025/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe run_tests.py（可从任意目录）。脚本将每个编译和可执行测试限制30秒，MinGW bin加入子进程PATH。O0/O2、C11/C++17、Wall/Wextra/Werror/Wpedantic 全通过：新增各4239检查（含100轮实际双线程BLE/voice扫描争用），原targeted各929、原完整200轮pthread+12客户端各44589、broker各10826。原始命令和输出见 test-output.txt。测试实际编译这些候选函数，块在硬件端口为明确 mock；其中的 IP 数字不是实机证据。

覆盖：BLE/VOICE互斥与错误owner、连接与扫描双向冲突、已在线不停止网络、外部占用、取消前未提交/运行取消、每一缺失清理fence保持held、stop失败重试、超时/回拨、提交拒绝、邮箱FULL、迟到报告/事件、ticket耗尽、不可变值拷贝、64项截断、非法SSID，IP不满足认证/DHCP/worker退出/有效地址不升级。

前两次完整回归超时已保留 regression-first/second-attempt.txt。已证实 harness 将 input 内旧头和当前对象混用，结构ABI不同；原始全基线 original-baseline-result.json 通过。修正 test_dispatch_current.c 先包含当前头，重新完整O0/O2通过。不是删除失败记录或将超时计为通过。

## 尚未覆盖

正式 app/SDK 构建、真实扫描/AP列表、STOP/CLOSE与固件event/RX排空协议、真实任务退出和持有维护连接的移交、SMP压力、内存不足抛异常的 C++ 平台策略、BLE加密epoch完整集成、CLI旁路关闭、NuttX栈/调度时延仍由主会话接入验收。scan侧 snapshot 与 collector 各固定64项，poll拷贝有界；C++结果最多64个字符串，需为异常/分配策略及任务栈核算资源。不能以主机测试宣布已经能真实语音配网。

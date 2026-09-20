# 共享 Wi-Fi 调度候选契约

本目录是统一仓库中的主机候选。C11 实现不分配堆内存；请求队列 8、事件队列 16、结果槽 16。网络后端与时钟在测试中模拟，线程和 mutex 使用真实 pthread。没有 openvela 编译或 WPA/DHCP 接入验收。

## 线程与端口

初始化在所有线程启动前完成，实例不可在运行中重置或销毁。生产者只调用公开 begin/poll/cancel/release/post API，不读写结构内部字段。`wd_pump` 为唯一 broker 所有者；重叠或回调重入返回 `WD_BUSY`，不得直接调用实例中的 `wb_*`。一个 pump 最多处理一个请求、一个事件，无网络等待。

`lock/unlock` 必须是有效、不可失败的互斥端口，提供跨核 acquire/release 可见性。主机用 pthread_mutex；NuttX 适配须处理 nxmutex_lock 的错误后才能进入临界区，不能忽略错误后继续。不能用仅关本核中断替代 SMP mutex，不能从 ISR 调用。队列锁内只有固定容量拷贝、擦除和元数据操作；不得嵌套 g_prov_lock、g_wifi_operation 或网络状态锁。

`now_ms` 为线程安全、非阻塞的单调 64 位毫秒时钟，所有调用同一时基。测试以 atomic 模拟确定性时间，不代表板端时钟已实现。不能直接采用会回卷的 32 位 prov_now；平台须提供安全扩展或原生 64 位时钟。排队时间计入总超时，回退报错。mutex 等待和后端回调自身的耗时由平台约束，代码不承诺硬实时。

`submit` 在队列锁外调用，只向固定后台工作槽非阻塞提交，返回 0 前必须完成凭据复制。非零返回必须保证没有启动工作或建立链路；已部分接受或无法证明未启动必须返回接受，稍后以完成事件报告失败。`stop` 只发停止请求；返回 0 不是退出证据，非零在以后 pump 重试。禁止在这些回调中执行阻塞的 prov_wifi_connect/fw_wifi_join_run。owner 服务循环可用有界定时唤醒，生产者也可另行发信号；唤醒机制不在此核心内。停止服务前必须停止生产者、排空请求、停止活动网络并确认清理围栏，不能强制销毁 mutex 来退出。

## 请求、身份与凭据

BLE 和 VoiceLink 分别经 wd_ble_* 和 wd_voice_*，内部固定 owner=1/2，不接受 JSON 或识别文本提供 owner。C 层是可信代码约定，不是进程安全隔离。同 owner 可访问本 owner 的票据；BLE epoch/连接会话隔离仍由上层负责。

dispatch ticket 与 backend broker id 是两个命名空间，不能混用。有效实例和 id 指针的尝试均消耗唯一 ticket，包含队列满/参数拒绝；耗尽后返回 WD_EXHAUSTED 和 0，不回绕。只有 WD_OK 的票据保留查询记录，拒绝结果直接消费、不继续 poll。非 live 历史槽按最老票据淘汰，随后查询 UNKNOWN；queued、running、draining、owned 槽不淘汰。队列满返回 WD_FULL，入队成功也可能稍后因网络资源被占用而得到 WB_BUSY，不是无界等待队列。

输入 SSID 长度 1..32、口令 8..63 且不含 NUL、超时非零。不支持开放网络。后端若传 C 字符串，须以长度复制到自身多一字节的缓冲并显式终止，不假设输入端有 NUL。调用者在 begin 返回后负责擦除自己的输入，候选仅擦除自己持有的队列/临时 job/broker pending；后端负责擦除其复制件。队列取消立即擦除仍在队列中的凭据，已取出的副本由 owner/worker 清理。volatile 擦除不等同于操作系统分页、编译器临时副本或取证级清除保证。

cancel/release 使用结果槽上的持久位，不需要额外队列空间。成功返回代表记录意图，状态在 pump 更新。并发 cancel 若晚于本轮取标志，可能先开始工作，再由下一轮停止；不能将 cancel 返回解释为 worker 已退出。cancel 对已经 OWNED 的网络无效，断开须 release。提前 release 的意图保留，在进入 OWNED 后的后续 pump 执行；上层要取消未完成操作应使用 cancel。公开 API 不自动取消 BLE 断连后的已接受配网。

## 事件与退出围栏

后端只发可信事件，携带 broker owner/id 和每事务严格递增、非零、不回绕 sequence。多个底层信号必须先经过一个事务监督发布者形成完整快照；不能让 DHCP 与退出线程各自独立生成序号、累积陈旧布尔值。旧 id、旧 sequence 被忽略。

WD_PROGRESS 不推进 broker 状态，带 IP 也不是联网成功。WD_COMPLETION 是权威完整快照。成功需同时 success、authenticated、dhcp、有效 IP、link_up 和 worker_exited。这里成功的 worker_exited 指连接操作线程已退出且网络维护已正式移交给 OWNED 租约；不意味着持续维护线程也已经结束。线程内部在 return 前发 semaphore 不能冒充线程已退出，平台须有 supervisor/join 或等价生命周期证明。

取消、失败和超时进入 DRAINING 后，迟到 IP 不得恢复成功。只有权威快照确认旧事务全部连接/维护工作已退出、接口离线且清理完成，才发布 worker_exited=true/link_up=false 并释放资源。停止请求已送达、局部离线、清理超时或固件 CLOSE 失败均不能释放。清理不成功可以持续 held=true，不抢占给重试者。

事件队列满时 WD_FULL，不覆盖旧事件。监督发布者必须保留并重试完成快照，成功排入后才推进后续序号；尤其不能丢退出围栏。可丢的进度与不可丢的完成应在后端分开管理，避免新进度使旧终结事件饥饿。队列拥塞期间结果可能滞后，不能作实时链路检测源。

## broker 最小修正

原 input/src/wifi_broker.c 在 OWNED 收到 offline=true（即 link_up=false）但 worker_exited=false 时仍保留 IP_READY。当前 src 副本改为立即 FAILED/DRAINING 并清空 IP，确认退出后才 FREE。专门测试覆盖离线先到、重试 BUSY、迟到成功、最终清理；没有改变身份或清理围栏。除此之外保留原 broker。

核心不打印日志，测试只打印轮数、检查数和失败行号，不打印口令。测试扫描原始运行输出中的测试口令；此检查不替代正式后端和 BLE 日志审计。

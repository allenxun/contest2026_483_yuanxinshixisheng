# 主会话集成变更定位（尚未应用）

以 input/sources.json 哈希对应的工作区源码为基础，不以 HEAD 代替未提交源码。正式接入前重新比对；本说明不表示修改已进入 app 或 SDK。核心新增 include/wifi_dispatch.h、src/wifi_dispatch.c，采用本目录修正后的 broker 副本；补丁在 candidate.patch。

| 正式位置 / 函数 | 所需替换及边界 |
| --- | --- |
| app/k7radio/prov_service.inc / prov_worker 的 PROV_CREDENTIALS | 保留仅接收凭据语义，不调用网络成功事件；wifi_connected=false。 |
| 同文件 / PROV_CONNECT 分支（快照约 232 行） | 将阻塞 prov_wifi_connect 改为 wd_ble_begin。固定槽记录 prov_epoch、请求 JSON id、dispatch ticket。入队成功后报 connecting，轮询结果到 IP_READY 才报 wifi_connected；FULL/INVALID/后续 BUSY 显式回包并释放通知事务 busy。不得在 g_prov_lock 下 pump/等待网络。 |
| 同文件 / prov_write_command、prov_disconnected、prov_send/LPWORK | 仍校验订阅和加密；通知继续在 LPWORK 串行。断连清理旧 epoch 回包映射，已接受工作默认继续，不给新 BLE 会话回旧结果。用户明确取消才调用相同 BLE owner 的 cancel。不能将协议 busy 当作 radio 所有权。 |
| app/k7radio/prov_wifi.inc / prov_wifi_connect | 拆为非阻塞 backend submit 和专用连接 worker。删除“发现已有网络自动断开并等待 5 秒再接管”的路径，OWNED/EXTERNAL 要返回 BUSY 或经显式 release + 清理证明。连接 worker 持有 g_wifi_operation 处理旧共享全局；不在队列锁下运行。 |
| app/k7radio/wifi_assoc_probe.inc / fw_wifi_join_run | 保留现有 WPA2/CCMP 和 supplicant 检查，增加事务 stop/deadline 观察点及权威结果收集。该函数会阻塞 scan/auth/WPA，不能直接作为 submit。成功通过 fw_wifi_ip_session 转移 supplicant 所有权，不能因 join 函数返回便证明维护线程退出。失败路径 clear_keys/unjoin/CLOSE 必须全部纳入清理证明；faulted 不允许释放。 |
| app/k7radio/wifi_ip_service.inc / fw_wifi_ip_worker、fw_wifi_ip_session、fw_wifi_ip_cleanup | DHCP ready 只发 PROGRESS。监督者等连接线程真实退出并确认维护租约移交后才发成功 COMPLETION。维护离线先发完整失败快照，全部退出且清理成功后再发最终离线/退出快照。ready/done 在函数 return 前发布，不能独立用作退出围栏。现有 timeout 后无界等 done 路径需改为有界等待加 held 故障状态，不得超时就假定清理成功。 |
| app/k7radio/k7radio_main.c / wifi-* CLI、scan 入口；wifi_auth_console.inc / fw_wifi_auth_console | 必须纳入同一仲裁或共享服务启用时显式拒绝旁路。CLI 原直接 g_wifi_operation/fw_wifi_join_run 和 g_wifi_network_stop 不再能够绕开租约。诊断扫描也占用无线资源，候选目前没有扫描请求 API，不得假定扫描已覆盖。 |
| parallel-voicelink 的 WifiPort 接入 | begin 经 wd_voice_begin，复制凭据后立即擦除 caller；返回非零 ticket，即时拒绝映射为 Busy/Invalid。WD_QUEUED/WB_RECEIVED 不是成功；WB_CONNECTING 为连接中，只有 WB_IP_READY 为真实成功，FAILED/TIMEOUT/CANCELLED/BUSY 分别处理。保留 held 对清理的门禁，退出时显式 release 已持有租约。原只读 voicelink_adapter.hpp 不可直接绕过调度器调用 broker。 |

平台实例由唯一服务管理，初始化 proven_offline=true 需要原连接及维护线程退出、网络离线、密钥/接口清理成功的证据。当前板端可能已有网络，不能默认 true。false 将维持 EXTERNAL/BUSY；核心没有未授权 takeover API。主会话可在受控启动顺序建立清洁初态。

服务所有者可在普通工作线程上定期 pump，接入事件/请求唤醒以缩短延迟。GPIO、BT LPWORK、网络 RX 不执行 pump 的阻塞 backend。需要明确 NuttX mutex、单调时钟、唤醒、任务创建/退出监督、后台工作槽、凭据擦除、退出事件重试缓冲和 SMP 亲和性。当前仅主机 pthread 实现这些测试端口，正式平台实现与编译仍待主会话。

后续板端验收应分别记录：两客户端竞争；真实 WPA/DHCP 和 IP 状态；取消后的迟到信号；退出/离线顺序；失败 CLOSE 的资源保留；BLE epoch 隔离；后台负载下队列满；服务停止/重启；并发扫描和 CLI 禁止旁路。不得将本目录的模拟 IP 192.0.2.1 或 200 轮主机测试记为这些实测。

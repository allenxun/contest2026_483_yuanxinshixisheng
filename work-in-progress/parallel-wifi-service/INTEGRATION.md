# 正式服务接口映射与补丁建议（未应用）

输入快照和 SHA-256 位于 evidence/inputs.json / input/；行号对应本轮快照，主会话集成前先核对漂移。下列是精确到入口和替换块的设计建议，不是可直接编译的固件补丁。

| 正式入口 | 现行为及必要改动 |
| --- | --- |
| prov_service.inc:204 `prov_worker`；232附近 `PROV_CONNECT` 分支 | 保留请求解析和外部 req.id/epoch，分配可信 owner token，调用 wb_begin 后立刻清除 req.password/ssid。保存 `{BLE请求id, epoch, owner, broker_id}` 映射。由服务任务轮询状态并发送 wifi_connecting/wifi_connected/error，不在通知回调中执行连接。只有 wb_take_job 进入 CONNECTING 后才报告实际开始。 |
| prov_service.inc:223 `PROV_CREDENTIALS` | 原功能只是接收回执，应继续清零并回复 wifi_connected=false；不要自动转成 broker 连接请求。 |
| prov_service.inc:49 `prov_disconnected` | 保持 epoch/订阅/传输缓冲清理，但不调用 wb_cancel。已被 broker 接受的请求继续。未被解析接受的传输缓冲仍可丢弃，与已接受语义分开。 |
| prov_service.inc:147 `prov_notify_work`、172附近 `prov_send` | epoch只管通知交付，不能决定射频所有权/取消；新会话不能接收旧 epoch 的结果推送，status 可查真实网络。当前 PROV_CONNECT 用 `if(!ret) prov_wifi_connect` 把通知成功与执行绑定，集成时需改成“接受后独立执行”，否则接受后BLE断开仍可能阻止工作开始。 |
| prov_wifi.inc:14 `prov_wifi_connect` | 删除16–24附近“active则stop旧连接并等待”的抢占路径。将目标SSID设置/恢复、fw_wifi_join_run封装为仅独立worker调用的backend入口；必须验证 broker owner/id 和唯一工作占用。保留 g_wifi_operation 作为底层互斥，但锁失败应报告失败/忙并清理，不越过 broker 启动另一操作。 |
| prov_wifi.inc:6 `prov_wifi_snapshot` | 现快照是全局状态，没有事务绑定。只能在该工作已认证、DHCP成功且事务/目标一致时用它填完成事件；旧连接的全局IP不得完成新事务。不要把 associate返回0当成 IpReady。 |
| wifi_ip_service.inc:50 `fw_wifi_ip_worker` | DHCP `lease==1` 后继续循环维护链路，不能把 DHCP 通知误作全部底层线程退出。成功连接工作完成后进 OWNED；该IP维护线程仍属于同一owner，任何新begin仍busy。 |
| wifi_ip_service.inc:79–84 清理与结束 | 当前先post g_wifi_ip_done再设置 network_active=false，单凭信号量不是退出栅栏。需要明确完成/移交握手：清理资源、断开链路并确认旧执行者不再操作，再向broker报告exited/offline；未确认继续DRAINING。实际顺序由主会话审查改动。 |
| wifi_ip_service.inc:105–114 启动/等待 | worker创建失败、DHCP等待失败均必须报告本事务结果，擦除临时凭据；等待和join不能在broker锁/LPWORK下运行。 |

建议新增统一服务任务（正式位置由主会话决定），由固定 mailbox/短临界区接收 BLE/VoiceLink 请求、worker完成事件、tick 和显式release。调用 wb_take_job 只复制工作，不运行网络；复制完解锁后交给独立worker。调度失败按契约清理。服务初始化先用 EXTERNAL；只有核对现有网络和工作者确实空闲，或为旧连接实现明确移交后才接管，不得init(..., proven_offline=1)猜测离线。

VoiceLink 适配示例 `include/voicelink_adapter.hpp` 使用冻结的原 WifiPort 头文件编译，没有修改上一交付。它只能在服务任务或相同短临界区内调用；若语音线程直接调用，需要消息代理。scan 明确 FatalError/-38，不生成假AP列表。backend通用失败暂映射 Failed，未区分认证密码错/找不到网络等板端具体错误；真实errno映射应追加类型字段，不能通过测试假设原因。默认服务超时30秒，与上轮控制器一致；产品超时预算需统一配置。

ID耗尽时adapter返回Failed/id0，由现有控制器零ID检查进入Error。示例依赖C++异常支持以捕获IP字符串分配失败，C11核心不依赖异常、动态分配或库运行时；NuttX C++配置仍需主会话确认。若IP字符串分配失败，broker成功连接仍OWNED，不允许他人抢占，需上层状态诊断/显式release。

日志禁止密码：broker不包含任何日志调用，history只有owner/id/status/IP；worker和BLE解析器分别负责清理自己的凭据副本。worker丢失或无法确认清理时保持DRAINING是预期安全停滞，没有假定超时就等于线程死亡。需要由主会话设计实际恢复策略。

本轮没有模拟真实DHCP或真实取消，仅以带明确标志的fake backend验证服务逻辑；未解决板端线程调度、消息容量、锁顺序、真实网络取消、扫描互斥或持久化。部署前应将所有CLI/诊断联网与扫描入口也纳入统一操作所有权，不能只约束BLE和语音却让旧控制台绕过服务。

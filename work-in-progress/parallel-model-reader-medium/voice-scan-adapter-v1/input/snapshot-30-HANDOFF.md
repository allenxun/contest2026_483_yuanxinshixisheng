# 语音扫描复用契约：未接入，NOT_READY

本交付是有证据的最小接口方案，不实现第二套broker/dispatch。`scan_contract.h`仅声明供未来集成讨论，不可直接链接部署。没有SDK/硬件访问，没有改正式源码或其他候选。源逐字冻结、SHA256见inputs.json；接口没有运行实现，因此没有运行测试或目标编译通过的声明。

## 当前真实边界

1. parallel-wifi-dispatch/include/wifi_dispatch.h 只有BLE/VOICE begin连接、poll/cancel/release、post/pump，没有scan。其INTEGRATION.md已明确扫描旁路尚未覆盖。parallel-wifi-service/include/voicelink_adapter.hpp 的 BrokerWifiPort::scan 返回FatalError/-38；不是成功空列表，也不是已有异步scan。
2. app/k7radio/k7radio_main.c:1192 `fw_wifi_scan`为同步阻塞：校准、OPEN、被动扫描22信道、8秒信号量/接收等待、必要STOP、CLOSE；总时限不等于8秒。CONFIG_EXAMPLES_K7RADIO_IP下network_active时返回-EBUSY，不断开在线网络。上层可将已知在线扫描能力映射Unsupported，但不能把所有-EBUSY都改Unsupported（连接/另一扫描争用是Busy）。当前VoiceLink IoStatus没有专用Unsupported扫描枚举，需由root明确UI映射或扩展接口，不能伪造IoStatus::Ok。
3. app/k7radio/prov_service.inc:249的PROV_SCAN在独立prov_worker上阻塞拿g_wifi_operation，然后fw_wifi_info/fw_wifi_scan；不在BLE LPWORK上跑扫描。g_prov_busy是协议事务busy，不是全局无线租约。连接成功后的维护线程仍持有网络资源，不能因g_wifi_operation可锁就允许新操作。
4. `prov_scan_report`:189通过skw_bss_decode真实解析，最多64项，按BSSID去重；RSSI更强则只替换scan记录，旧security未跟着更新，这是直接复用现有表时需知的字段一致性缺口。`fw_wifi_scan_report`:732在消息类型11接收路径调用该收集器；底层另一份g_wifi_seen只做诊断去重，不能当完整安全类型列表。语音不能直接借g_prov_scanning/g_prov_aps：BLE断连会清标记、epoch独立且数组有异步RX写入。
5. app/k7radio/prov_wifi.inc:14 `prov_wifi_connect`当前还会在线时设置network_stop并等最多5秒，再join。统一服务接入必须移除该自动接管路径或禁用旧入口，否则语音与BLE仍可绕broker竞争；不能因为VoiceLink核心迁入app就宣布无线仲裁完成。

## 最小接口与接入点

建议未来service唯一owner在处理连接请求同一个pump调度边界原子取得SCAN租约。只有broker FREE、无旧worker/维护任务、真实离线且无扫描可启动；QUEUED/RUNNING/DRAINING/EXTERNAL均Busy；OWNED且在线返回明确Unsupported，绝不为扫描断网。开始扫描后，同一仲裁必须挡住BLE/VOICE连接与CLI扫描/认证入口，直到退出及CLOSE成功的证明完成。仅新增独立scan mutex不满足此要求。现有broker没有SCAN状态，此处需要主会话批准并实现最小服务扩展，不能在候选外部读broker.radio再调用（存在检查/使用竞态）。

`voice_scan_begin/poll/cancel`建议非阻塞；固定VOICE身份由可信调用点注入，ticket/generation由service发放，模型/识别文本不提供owner/id。一个固定64项结果槽即可首轮，Busy直接拒绝重叠，不做自动排队/合并。专用worker调用现有fw_wifi_scan，回调写单独service collector；统一collector从skw_bss_decode得到记录，复制完整SSID bytes/len、BSSID、RSSI、security/band/channel。BLE原JSON输出及语音适配均读取完成后的不可变拷贝，不共享g_prov_aps可变表。SSID长度0..32、非UTF8/控制字符/空SSID不可静默转换成另一个SSID；展示名与连接字节保持独立，无法语音选择者保留为不可选。

收集器结束时先在锁内关闭收集，确认接收回调不再引用槽，再冻结结果。固件扫描report本身没有当前候选定义的事务ID；本地generation不能证明迟到旧帧来源。必须证明STOP/CLOSE与RX排空/完整scan_done的关联，未证明前不启动下一扫描，超时/清理失败保持held。worker在return前发信号也不能证明已退出，应由supervisor负责。cancel只是取消意愿，不是stop完成；不能丢退出围栏事件或因BLE断连释放租约。

精确改动位置（此交付不应用）：

| 位置 | 接入动作 |
|---|---|
| wifi_dispatch.h/c 的服务pump边界 | 增加同一仲裁中的扫描租约/拒绝连接规则，保留现有连接票据及所有权契约 |
| k7radio_main.c fw_wifi_scan_report / type11 RX | 把已解码真实report路由到服务collector；不让语音设置BLE全局标志 |
| k7radio_main.c fw_wifi_scan | worker内调用；返回失败时额外保留STOP/CLOSE/退出证明，单int返回不足以表达清理是否安全 |
| prov_service.inc prov_worker PROV_SCAN | 变为同一service的BLE扫描请求；保留epoch、加密订阅与LPWORK通知门禁 |
| prov_service.inc prov_disconnected/prov_send | 仅丢旧epoch回包映射，不自动撤销另一个owner的radio工作 |
| prov_wifi.inc prov_wifi_connect / CLI wifi-* / wifi_auth_console.inc | 移入同一仲裁或服务启用时拒绝旧旁路，不能保持自动断网接管 |
| VoiceLink WifiPort::scan | 当前同步接口不能在控制线程等待8秒；应使用未来begin/poll扫描状态，或在已授权服务工作任务适配，root需确定控制核心接入方式 |

## 密码与事务

扫描请求/快照绝不含密码。连接沿用wd_voice_begin，caller在凭据复制后立即擦除自身输入；dispatcher/backend各清自己的拷贝。凭据接收、connecting与IP_READY严格不同：PROV_CREDENTIALS现有逻辑仅验证接收并擦除，不连接；只有权威WPA/DHCP/真实IP及退出/维护移交快照才连接成功。声学输入密码属于本地敏感路径，不进入云LLM、TTS回读或日志。BLE JSON id/epoch与dispatch ticket不可混用，声音文本不能生成DeviceEvent或伪造完成。

后续测试应在主会话唯一service实现上增加：BLE扫描与VOICE连接互斥、反向争用、在线Unsupported且没有STOP/CLOSE副作用、EXTERNAL/DRAINING保持Busy、扫描超时且CLOSE失败held、迟到报告不污染新generation、断BLE保留VOICE事务、64项truncated/重复BSSID整记录一致性、二进制SSID精确保留、密码不出现在结果/日志。当前只给这些验收条件，不声称模拟通过或无线已接入。

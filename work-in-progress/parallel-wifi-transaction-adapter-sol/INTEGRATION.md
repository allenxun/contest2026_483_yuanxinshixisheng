# VoiceLink → k7radio 连接事务接入点

本候选不修改正式源码。目标是替换 `app/voicelink/src/voice_wifi_adapter.cpp` 中连接部分的三项薄映射，扫描仍转发给现有共享扫描端口。Controller ABI 可以保持不变：Accepted 映射 `CredentialsReceived`；InProgress、Authenticated、Dhcp 均映射 `Connecting`；只有严格的 IpReady 映射 `IpReady`。认证与 DHCP 的细阶段保存在 `lastProgress()`，供诊断使用，不能触发成功播报。

## k7radio 服务接口

1. `app/k7radio/wifi_dispatch.h` 的查询快照需要增加 `sequence`、事务阶段、失败原因、`authenticated`、`dhcp_acquired`、`link_up`、`lease_held`、`operation_complete` 和 IPv4。`transaction_id` 必须沿用服务 ticket，不能使用 BLE JSON id 或语音文本中的值。
2. `app/k7radio/wifi_dispatch.c:k7wd_post/k7wd_pump` 当前接收 `WD_PROGRESS`，但 pump 只对 `WD_COMPLETION` 调用 `wb_complete`，随后发布的仍是 broker 粗粒度结果。应将严格递增的 PROGRESS 写入同 ticket 的只读查询快照；旧序号、重复序号和非活动 ticket 不得覆盖新状态。COMPLETION 继续负责终态和释放栅栏。
3. `app/k7radio/radio_backend_state.inc:rb_authenticated` 是认证成功的真实观测点。它应在退出 `rb_lock` 后发布匹配 owner/id 的 Authenticated 进度，不能在锁内回调 dispatcher。
4. `app/k7radio/wifi_ip_service.inc:fw_wifi_ip_worker` 中 `lease==1` 是 DHCP 租约和 IP 的真实观测点。这里发布 Dhcp 进度并保存事务绑定的 IP；全局旧 IP 不得完成新事务。
5. `app/k7radio/radio_backend.inc:rb_post_connect` 当前使用 `e.done.dhcp=success`，这会把汇总成功位当成 DHCP 事实。正式接入应从事务事实快照取 `authenticated/dhcp`，并只在 worker 已结束或已明确把持续维护移交给 OWNED、链路在线、租约仍持有且 IP 合法时发布 IpReady COMPLETION。
6. `fw_wifi_join_run` 的错误需保留为事务失败原因：`-EACCES`→Authentication，`-ENOENT`→NetworkNotFound，`-ENOTSUP`→UnsupportedSecurity，其他→Backend。不得从超时猜测密码错误。
7. `k7wd_voice_cancel` 只请求取消。dispatcher 继续持有射频，直到匹配 completion 证明清理/移交完成；适配器本地屏蔽同 ticket 的迟到 IpReady，避免取消后反转成功。

## VoiceLink 接入

- `app/voicelink/src/voice_wifi_adapter.hpp/.cpp`：扫描方法保留；连接方法改为本候选的 submit/poll/cancel 语义，或让 `SharedWifiPort` 内部复用本候选的转换逻辑。
- `app/voicelink/include/voicelink/types.hpp` 无需为第一轮接入增加成功状态。Authenticated/Dhcp 对 Controller 都是进行中；若以后需要分阶段提示，再单独扩充 UI 状态，不能改变完成门槛。
- `app/voicelink/src/core.cpp:Controller::tryConnect/applyConnectResult/poll` 已具备关键门禁：提交后进入 CredentialsReceived；事务 ID 不同的结果被丢弃；本地期限在同刻 IP 前获胜；只有 `IpReady` 和有效 IPv4 完成。保留这些检查。
- `app/k7radio/prov_wifi.inc:prov_wifi_connect` 目前自身阻塞轮询共享事务。VoiceLink 不应调用该 BLE 包装入口，而应调用 dispatcher 的 voice owner API，避免把通知、BLE epoch 或同步等待混进语音 Controller。

## 合入顺序

1. 先为 `k7wd_view` 增加只读字段及 progress 单元测试，验证序号单调、旧 ticket、队列满、取消后迟到事件和超时。
2. 再接认证与 DHCP 的真实发布点，保留错误码，做 ARM64 编译和 ELF/接口核对。
3. 最后替换 VoiceLink 连接适配，并复跑正式 19 项 Controller 流程及本候选假后端测试。
4. 真机只在独立固件上验证 Accepted→Authenticated→Dhcp→IpReady 的同 ticket 原始输出，并分别做错误密码、找不到网络、取消、期限边界和旧事件注入。任何一步都不能把 `credentials_received` 当成联网成功。

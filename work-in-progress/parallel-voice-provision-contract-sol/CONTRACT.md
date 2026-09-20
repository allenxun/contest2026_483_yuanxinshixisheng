# 纯板端规则语音配网候选契约

本候选只定义编排逻辑，不实现 ASR、KWS、TTS、音频驱动或无线后端。调用任务把 ASR 的有限词表结果串行交给 `Machine::ingest()`，并以不大于 50 ms 的周期调用 `poll()`。所有 TTS 文本均为固定模板；状态机不会把密码内容、密码字符或无线凭据传给播报和日志接口。

流程为：指定唤醒词 → 异步真实扫描 → 最多五个 SSID 按信号排序播报 → 编号选择 → 逐字符有限词表输入 → 只播报长度 → 强制二次确认 → `submitCredentials` → 同事务 WPA2/DHCP 权威事件 → 有效 IPv4 后如实播报成功。确认词只有“确认”或“确认提交”；“完成”只进入确认态，任意其他文本均不得提交。否认、重输、取消、超时和析构都擦除候选持有的密码。

有限密码词表包括单个 ASCII 可打印字符、零至九、艾特、井号、下划线、减号、点、正/反斜杠，以及删除、清空、重新输入、完成、取消。一次话语只能形成一个字符。生产接入时可直接复用 `app/voicelink` 的更完整字符解析器，但必须保留本候选的 `ConfirmingPassword` 门禁。

无线适配边界：

- 扫描对应 `app/k7radio/scan_contract.h` 的 VOICE 身份、唯一 ticket、不可变 snapshot 与 held 清理约束。
- 提交对应 `k7wd_voice_begin`，也就是 BLE JSON `submit_credentials` 使用的同一 `wifi_dispatch`/`wifi_broker` 后端；owner 身份由受信适配器选择，不接受语音文本提供 owner 或事务号。
- `CredentialsAccepted` 只表示复制接收，绝不表示联网成功。
- `Wpa2Authenticated`、`DhcpAcquiring` 必须来自真实后端事件。当前 `k7wd_view` 只有 `WB_CONNECTING` 与 `WB_IP_READY`，因此正式集成前需要把已有 `wb_done.authenticated/dhcp` 作为单调、同事务进度事件安全暴露；不能从耗时、字符串或模型输出猜阶段。
- 只有同一 request ID 的 `IpReady` 且 IPv4 可用才进入 Completed。迟到或其他事务事件被忽略；截止时刻到达的成功也由超时优先处理。

扫描、输入、连接默认分别为 30、60、30 秒。Busy、Unsupported、Timeout、Cancelled 返回 Idle，可重新唤醒；协议破坏、无事务号、无效 IP、一般失败进入 Error。WrongPassword 回到空密码输入，NetworkNotFound 回到选网。取消是事务级且幂等，不得断开其他所有者已有连接。

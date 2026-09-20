# 接口与集成说明

## 依赖的正式契约

- `voicelink::Controller` 是唯一规则状态机。候选不解析唤醒词、SSID 编号、密码字符或确认语句。
- `voicelink::ClockPort` 提供单调毫秒时间。Controller 自己裁决扫描和连接超时；候选只裁决录音和 ASR 阶段超时。
- 正式 `SharedWifiPort` 继续连接 `k7radio` 的共享扫描服务和共享连接 dispatcher。候选从不直接调用无线驱动，也不构造成功 IP。
- `k7_asr_microphone_text(char*, size_t)` 是现有“读取最后一次完整录音并识别”入口。板端 `AsrPort` 应在工作任务中调用它，不得把它的内部模型、线程局部存储或音频复制逻辑搬进本层。

## CapturePort

`begin(grammar)` 为一条语句启动录音，并返回生命周期内不复用的事务号。`Complete` 表示该事务对应的录音已停止且内容不可再变。`release(id)` 同步结束编排层对句柄的使用；失败和取消路径也必须可重复调用。真实适配器应复用 `k7sound` 的音频所有权和完整录音快照，不得把诊断录音当普通 ASR 输入。

## AsrPort

`begin(capture_id, grammar)` 消费一个完整录音句柄。实现可同步返回 `Ready`，也可返回 `Accepted/Recognizing` 后由 `poll()` 完成。事务号同样永久不复用。取消是针对单笔事务的幂等请求；ASR 结束后 Loop 才释放录音句柄。

当 grammar 为 `PasswordToken` 时，适配器不得打印、追踪、持久化或发送识别文本，也不得把文本放进错误消息。`AsrResult::text` 交给 Loop 后视为转移所有权；Loop 在一次 `Controller::ingest()` 返回或异常展开时覆盖其字节。端口自己的临时副本也必须清零。

## Loop 驱动规则

单一协调任务创建一次 `Controller` 和一次 `Loop`，调用 `start()`，随后建议每 50 ms 以内调用 `tick()`。Loop 在 `WaitingWake`、`WaitingNetworkChoice`、`EnteringPassword`、`ConfirmingPassword` 四种 Controller 状态开始新录音；在 `ScanningWifi`、`CredentialsReceived`、`ConnectingWifi` 只轮询 Controller。

端口忙时 Loop 延迟后重试，不伪造输入失败。事件事务号与当前录音/ASR 不相等时视为旧事务并丢弃。单调时钟回退进入错误。截止点与结果同时发生时，超时优先。调用 `cancel()` 会先取消 ASR、取消并释放录音，再调用 Controller 取消其当前扫描或连接事务。

Controller 的结果决定后续动作：开放网络仍进入 `ConfirmingPassword`，只有“确认提交”才允许空密码连接；密码错误回到密码输入；不支持或找不到网络回到网络选择；有效 IPv4 才进入完成状态。

## 固定提示与日志

Loop 不实现 TTS。现有或后续固定提示播放器只需实现 Controller 的 `TtsPort`；播放失败仍由 Controller 进入 Error。Loop 没有日志回调或 transcript getter，外部状态观测只暴露 phase、轮次计数和数字错误码。不得在端口日志中加入密码、完整识别文本或连接凭据。

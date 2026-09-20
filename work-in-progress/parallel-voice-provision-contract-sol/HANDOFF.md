# 纯板端规则语音配网候选交接

交付范围严格限制在 `work-in-progress/parallel-voice-provision-contract-sol/`。没有修改 `app/`、`board/`、`port/`、SDK、设备、无线状态或其他候选；没有使用真实 SSID 密码，没有实现或运行 ASR/TTS 引擎。

候选提供 C++17 纯逻辑状态机、端口接口、状态迁移表、无线事件映射边界及 10 条主机测试。关键变化是强制 `ConfirmingPassword`：用户说“完成”只进入确认态，只有随后独立说“确认”或“确认提交”才调用 `submitCredentials`。密码内容不进入 Snapshot、TTS 或测试输出，否认、取消、错误、超时与析构均擦除本地副本。

连接成功严格绑定同一 request ID 的真实事件。`CredentialsAccepted`、WPA2 认证、DHCP 获取和有效 IPv4 被分别建模；迟到或其他事务事件无效，超时优先。当前正式 `k7wd_view` 尚未分别暴露 `wb_done.authenticated/dhcp`，集成者必须先补充权威进度映射，不能从 `WB_CONNECTING`、耗时或模型文本猜测阶段。只有 `IpReady` 与可用 IPv4 才播报成功。

O0/O2 均以 `-Wall -Wextra -Wpedantic -Werror` 编译并运行通过，输出为 `10 contract scenarios passed; ports simulated; no credential value printed`。结果摘要见 `evidence/results.json`，完整文件哈希见 `SHA256SUMS.txt`。

输入基线来自正式 `app/voicelink` 的类型、端口、控制器、核心与原生 Wi-Fi 适配器，以及 `app/k7radio` 的 provisioning 协议、broker、dispatch 和扫描契约。它们仅被读取，输入哈希记录在 `INPUTS.sha256`。

后续集成顺序：先评审本候选的确认门禁与事件契约；再让共享无线服务发布同事务的认证/DHCP 权威进度；最后把 `Machine` 或等价迁移合并进正式 VoiceLink，并用实际 ASR 受限词表、固定 TTS 资产、真实 WPA2/DHCP 及取消/超时做板端验收。本候选本身不构成板端语音配网成功证据。

# 交付说明

## 结论

现有正式 `SharedWifiPort::beginConnect` 已把服务接受映射成 `CredentialsReceived`，Controller 也只在 `IpReady` 与合法 IPv4 时完成，这是可保留的正确边界。缺口在 k7radio 查询面：`WD_PROGRESS` 没有形成可查询阶段；认证与 DHCP 没有各自的事务事件；当前最终发布用汇总 `success` 代填 DHCP。候选为这些缺口定义了固定事务快照和 VoiceLink 映射，并用正式 Controller 做了假后端回归。

适配器不要求修改 Controller ABI。Accepted 只显示凭据已接收；InProgress、Authenticated、Dhcp 都显示连接中；IpReady 必须同时具备 authenticated、dhcp_acquired、link_up、lease_held、operation_complete 和合法单播 IPv4。失败、取消和 timeout 是终态。旧事务保留原 ID让 Controller 丢弃；同事务旧序号返回最近的新状态，不能倒退；取消后迟到成功在适配器侧保持 Cancelled。

## 验证

最终通过结果以按目录名排序的最新 `evidence/run-*/result.json` 为准。O0/O2 均以 `-Wall -Wextra -Werror -pedantic` 编译候选并链接正式 `app/voicelink/src/core.cpp`、`parsers.cpp`；两次原始输出均为 `wifi transaction adapter: 10 scenario groups passed; fake backend only`。

保留的失败：

- `run-20260912T091046068797Z`：默认 Python 3.6 不支持 `subprocess.run(text=...)`，没有进入编译；随后改用 `universal_newlines=True`。
- `run-20260912T091104919478Z/build-O0.raw.txt`：严格编译发现 range-loop 复制告警并按 `-Werror` 失败；改为 const 引用后通过。

## 未完成

- 未修改或编译正式 k7radio dispatcher/backend，未做 ARM64 固件构建或 ELF 核对。
- 未在真实认证和 DHCP 观测点发布 progress，未验证事件队列满后的重试与严格序号。
- 未做真实 WPA2、错误密码、网络不存在、DHCP 超时、用户取消、旧事件注入、链路丢失或长期运行。
- 未触设备、串口、VM、SDK、中央 AI 日志、eMMC、STM32 或云台。
- 未改 VoiceLink 语音循环、ASR runtime 或提示音。

正式接入位置与顺序见 `INTEGRATION.md`。合入前应重新核对正式文件哈希，因为本交付没有冻结主项目并发改动。

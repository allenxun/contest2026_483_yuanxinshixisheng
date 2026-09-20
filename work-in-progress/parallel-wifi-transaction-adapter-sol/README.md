# Wi-Fi transaction adapter 候选（sol）

这是 VoiceLink Controller 对接现有 k7radio 共享真实 Wi-Fi 服务的隔离候选。它没有改动 `app/`、SDK、设备、串口、VM 或中央日志，也没有重写语音循环、ASR runtime 或提示音。

候选明确区分：凭据已复制接受、工作已开始、认证完成、DHCP 进行/完成、带有效 IPv4 的最终成功、失败原因、取消、服务超时，以及旧事务/乱序事件。当前正式 Controller 只需要三类外部状态：CredentialsReceived、Connecting、IpReady；认证和 DHCP 保持为进度，绝不被翻译成成功。

复现命令（项目根目录）：

```powershell
python work-in-progress/parallel-wifi-transaction-adapter-sol/run_tests.py
```

脚本用系统 `g++` 在 O0/O2 下严格编译候选、正式 `app/voicelink/src/core.cpp` 和解析器，然后运行 10 组假后端场景。每次执行的完整命令、原始编译输出、原始测试输出、可执行文件哈希及源码哈希写入本目录 `evidence/run-*/result.json`。

覆盖范围：accepted 仅为 CredentialsReceived；in-progress/auth/DHCP 均不成功；IP 缺少任何认证/DHCP/链路/租约/完成条件均拒绝；失败原因映射；取消幂等且屏蔽迟到成功；服务 timeout；同事务乱序不回退；旧事务保留原 ID；正式 Controller 在最终 IP 前不播报连接。

限制：全部结果来自 Windows 主机假后端。未编译 ARM64 固件，未接真实 k7radio progress 发布，未执行 WPA2、DHCP、链路保持、真实取消或真机旧事件注入。具体正式接入点和真机门禁见 `INTEGRATION.md`。

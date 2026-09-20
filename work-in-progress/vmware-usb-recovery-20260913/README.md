# VMware / USB 只读恢复审计

本目录把 CH340 `/dev/ttyUSB0` I/O error 与 Rockchip USB download gadget 的恢复链路拆成可自动诊断和必须人工执行两部分。`inspect.ps1` 不打开串口、不发送 Fastboot 命令、不重启服务、不结束进程、不改驱动、VMX、注册表或 sysfs。它只读取 Windows PnP/VMware 状态，并可经固定 SSH host key 读取 Ubuntu 的 `lsusb`、udev、sysfs、占用者和内核日志。

## 结论

当前故障不能在这些约束内安全自动修复。2026-09-13 21:31 的来宾检查显示：

- VMware Tools `12.3.5.46049` 正常，CH340 `1a86:7523` 和 `/dev/ttyUSB0` 都存在。
- `/dev/ttyUSB0` 为 `0666`，`fuser` 没有发现占用者；udev 已加载项目现有的 `99-ch340.rules`。
- CH340 在 sysfs 中 `authorized=1`、`power/control=on`、`runtime_status=active`。
- 内核仍连续报告 `failed to send/receive control message: -110` 和 `failed to read modem status: -110`。这发生在 udev 命名与权限处理之后，是 USB 控制传输超时，不能靠重载 udev 或修改权限修复。
- `18d1:4d00` gadget 最近一次在 20:27 枚举，20:28 已断开，当前 Ubuntu 不存在该设备。来宾无法凭空创建板端 gadget；它必须由 U-Boot 的 `fastboot usb 1` 产生。

Windows 同期 `VMUSBArbService` 为 Running/Automatic，`vmware-vmx` 仍在运行，PnP 没有当前 Code 43。Windows 只显示一个 Started 的 VMware USB 代理，物理 CH340 端点显示为 Disconnected，符合设备当前由虚拟机持有的状态。此时重启仲裁服务没有证据收益，并会同时扰动别的 USB 设备。

## VMware CLI / VIX 边界

本机为 VMware Workstation 16.2.1，`vmrun` 1.17.0 位于 `D:\software\VM\vmrun.exe`。它提供 `connectNamedDevice`、`disconnectNamedDevice` 与 `writeVariable`，但没有枚举可连接物理 USB 的命令。只读查询确认运行中的 VM 为 `D:\VMware\Ubuntu 64 位\Ubuntu 64 位.vmx`，Tools 状态为 running、IP 为 `192.168.152.131`。当前 `usb.autoConnect.device0..2` runtimeConfig 都为空，VMX 本身也没有持久化 `usb.autoConnect` 规则。

历史已验证 `usb.autoConnect.device0 = "vid:18d1 pid:4d00 autoclean:0"` 会在 Ubuntu 启动时卡住 VM，并曾使 VMware USB 代理进入 Code 43。不能把 `vmrun writeVariable` 或 VMX 自动接管规则作为无人值守恢复。即使能调用 `connectNamedDevice`，它也只能连接已被主机正常枚举且已有稳定虚拟设备名的设备，不能修复主机代理 Code 43 或板端未创建 gadget。

VMware Tools 提供来宾状态和命令通道，不控制主机 USB 仲裁。udev 只在 Linux 内核已经枚举设备后设置名称、权限和链接；它不处理主机代理、物理断连或控制传输超时。

## 安全状态机

| 检查结果 | 判断 | 最小动作 |
| --- | --- | --- |
| Windows/Ubuntu 都无 CH340 | 串口未枚举 | 人工重插串口线；等待 Windows 显示设备 OK，再从 VMware 菜单把 CH340 连接给 Ubuntu。 |
| Ubuntu 有 CH340，且日志出现 `-110`，没有占用者 | VMware/物理 USB 传输已失活 | 从 VMware “Removable Devices” 断开并重新连接**这一个** CH340；若仍超时，物理重插串口线。不要杀 `vmware-vmx`。 |
| Windows 有 Code 43 | 主机代理/设备枚举失败 | 采用已经验证的物理重插，或由有管理员令牌的人重启 `VMUSBArbService`；之后重新检查。脚本不自动提权。 |
| CH340 可用，`18d1:4d00` 不存在 | 板端 gadget 尚未运行 | 人工通过串口回到 U-Boot，拦截自动启动并执行 `fastboot usb 1`。这会写串口，所以不属于本只读检查器。 |
| Windows 看到 `18d1:4d00`，Ubuntu 看不到 | gadget 未交给来宾 | 等 Ubuntu 完全启动后，从 VMware “Removable Devices” 连接 Rockchip USB download gadget。 |
| Ubuntu 同时看到 `1a86:7523` 与 `18d1:4d00` | 传输前置条件成立 | 交给独立的、带哈希与地址门禁的 RAM-only 下载脚本；每次板端 reset 后重新校验所有保留模型 CRC。 |

若 `fuser` 报告串口占用者，只停止确认是遗留的串口客户端；不要停止 VMware 进程或服务。当前实测没有占用者，因此停止进程不会解决这次 `-110`。

## 使用

仅检查 Windows：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\inspect.ps1 -SkipGuest
```

同时检查 Ubuntu，并把结果写到一个新文件：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\inspect.ps1 -OutputPath .\diagnostic-YYYYMMDD-HHMMSS.json
```

脚本拒绝覆盖已有报告。SSH 使用现有私钥和已固定的 `known_hosts`，禁用密码回退；当前令牌读不到密钥时只报告 guest probe unavailable，不修改密钥 ACL。

## 证据来源

- `docs/USB快速RAM加载接续_20260911.md`：开机自动接管导致 VM 卡死、Code 43 与恢复边界。
- `docs/OTG恢复与语音复测_20260913.md`：板端软件 reset、重进 Fastboot 后从 Code 43 恢复为 Code 0 的有限真机结果。
- `docs/离线TTS语音配网接入_20260913.md`：20:25 串口/OTG 恢复、模型 CRC 重新校验及当前 TTS 上板阻塞。
- `evidence/voice-rule-wakepartial-20260912/`：管理员服务重启、代理重启、隔离和删除旧实例的原始结果；这些历史脚本会修改系统状态，本目录没有复用它们。

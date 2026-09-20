# VMware OTG 无人值守热接入审计

审计时间：2026-09-13 21:40–21:48（Asia/Shanghai）

范围：只读检查 VMware Workstation、Windows PnP、VMX/日志和现有 RAM-only Fastboot 加载器。没有连接或断开 USB，没有重启服务、虚拟机或板子，没有修改驱动、VMX、注册表，也没有传输数据。

## 结论

当前安装的 VMware Workstation 16.2.1 没有一个受支持的 `vmrun` 命令可以按 VID/PID、序列号、友好名称或物理路径，把一个尚未配置为虚拟硬件的物理 USB 设备热接入来宾。现有 `connectNamedDevice` 面向 `sound`、`serial0`、`ethernet0`、`sata0:1` 这类虚拟机配置中的设备名，不是物理 USB 枚举接口。

本机日志已经做了直接反证：

- gadget 的稳定物理标识是 `vid:18d1 pid:4d00 path:1/0/4 serialnum:F71A9D152132DB55`。
- 2026-09-13 12:27:17Z 的人工菜单操作产生 `USB: Connecting pattern [path:1/0/4]`，随后出现 `virtPath:ehci:0` 和 `ownerdisplay:Ubuntu 22.04 64 位`，说明这条 UI 路径确实能正确热接入。
- 2026-09-13 13:30:18Z 执行 `connectNamedDevice` 并传入 `vid:18d1 pid:4d00`，VMX 明确记录 `Attempting to connect nonexistent device`。
- 2026-09-13 13:32:32Z 改用 `Google USB download gadget` 仍得到同一条 `nonexistent device`。

因此，满足“无需人工点击、无需持久 autoconnect、无需改驱动/重启 VM/杀进程”的唯一合理方向，是**自动调用 VMware 已有的可移动设备 UI 动作**。它等价于用户点击“VM → Removable Devices → Google USB download gadget → Connect (Disconnect from host)”，并且是一次性的、可逆的，不写 VMX。当前 Codex 命令执行上下文却无法取得正在运行的 VMware 主窗口：真实 `vmware`/`vmware-vmx` 进程存在，但 `MainWindowHandle=0`，现有 `inspect_ui.ps1` 返回 `VMware window not found`。在这个上下文中不能可靠执行 UI Automation；如果产品之后提供可见的原生 VMware 窗口控制面，才可使用这一方案。

没有原生窗口控制面时，仍需要用户做一次 VMware 菜单连接。现阶段不存在可审计、无需改系统状态的 CLI 替代方案。

## 为什么 `vmrun connectNamedDevice` 不适用

本机 `vmrun.exe` 为 1.17.0 build-18811642。其帮助只接受 `connectNamedDevice <vmx> <device name>`，没有列举主机 USB、按 USB pattern 连接或调用 USB Arbitrator 的命令。Workstation 17 用户手册对 `device name` 的示例也是 `sound`、`serial0`、`Ethernet0`、`sata0:1` 等已配置虚拟设备。

VMware 内部确实有另一条物理 USB 路径：二进制中存在 `VUsb_AddDevice(controller, device, sticky)`、`VUsb_RemoveDevice` 和 `VUsb_SetPluginAction`，日志中的人工连接也是经 USB Arbitrator 按 `path:1/0/4` 执行。公开 `vmrun` 没有暴露 `VUsb_AddDevice`，不能把物理设备描述串伪装成 `connectNamedDevice` 的设备名。反向调用未公开的 Vigor/VMDB RPC 会依赖私有 ABI，可能连错 USB、破坏 VM 状态或在 Workstation 更新后失效，本项目不应采用。

Broadcom 官方文档也把 Workstation 的物理 USB 连接方式限定为：

- UI 中选择 Removable Devices 后连接；
- 在 VM 关机时编辑 `.vmx` 加 `usb.autoConnect.deviceN`，在 VM 启动或设备重新插入时自动连接。

参考：

- [Broadcom KB 418689：通过可移动设备菜单连接 USB](https://knowledge.broadcom.com/external/article/418689/connecting-usb-devices-to-a-virtual-mach.html)
- [Broadcom KB 343950：Workstation USB autoconnect 的 VMX 规则及风险](https://knowledge.broadcom.com/external/article/343950)

## 为什么不采用临时或持久 autoconnect

历史备份 `Ubuntu 64 位.vmx.pre-otg-recovery-20260912-2050` 中有：

```text
usb.autoConnect.device0 = "vid:18d1 pid:4d00 autoclean:0"
```

当前运行 VMX 已经没有该规则。项目证据记录这类自动接管曾与 VM 卡顿、USB 代理 Code 43 同时出现；官方文档也要求 VM 关机后修改 VMX，并警告冲突规则可能破坏虚拟机 USB 功能。它还不是“当前已枚举设备立即热接入”的保证：规则通常在 VM 启动或设备到达事件上生效。

`vmrun writeVariable ... runtimeConfig usb.autoConnect.device0 ...` 没有官方资料证明会触发物理 USB 热插，且当前执行上下文甚至无法稳定把运行中的 VM 识别为 powered on。`usb.generic.pluginAction` 是全局 ASK/HOST/GUEST 策略，不是带序列号的单设备连接接口；将它设为 GUEST 可能接管后来到达的其他 USB。两种方法都不应在无人值守板端传输中试用。

## 为什么 Windows 不能直接完成当前 RAM-only Fastboot 传输

Windows 当前把物理 gadget 列为：

```text
USB\VID_18D1&PID_4D00\f71a9d152132db55
USB download gadget
Class: Unknown
Status: Problem
Problem Code: 28 (CM_PROB_FAILED_INSTALL)
```

Code 28 表示没有绑定可供用户态访问的设备驱动。现有 `fastboot_ram_download.py` 使用 PyUSB，并要求能枚举设备、读取序列号、取得配置、声明 `ff/42/03` 接口和访问 bulk endpoints。Windows 上仅有 `libusb-1.0.dll` 文件并不足够；设备还需要绑定 WinUSB/libusbK/Google Fastboot 一类驱动。安装或替换这类驱动会改变主机驱动状态，并可能与 VMware USB Arbitrator 竞争，超出本次约束。

当前也没有发现已安装的 `fastboot.exe`、`usbipd`、`UsbDk` 或可直接复用的 WinUSB 绑定。因此不能在不改驱动的前提下从 Windows 直接发送这 116 MB RAM 包。

Windows 上的 `USB\VID_0E0F&PID_0001`、驱动 `oem38.inf` 是 VMware 代理端点，不是可以由 Fastboot 客户端直接打开的原始 `18d1:4d00`。代理驱动只服务 VMware 的 USB 转发链路。

## 可执行的安全方案

### 方案 A：可见 VMware 窗口下的 UI Automation（推荐）

只有在自动化环境能看见真实 VMware Workstation 窗口时使用：

1. 先只读确认 Windows 恰好有一个 `VID_18D1&PID_4D00`，序列号为 `F71A9D152132DB55`，状态不是 Code 43；同时确认 `VMUSBArbService` 为 Running。
2. 枚举真实 Workstation 顶层窗口。不要只依赖 `Get-Process.MainWindowHandle`；应使用 `EnumWindows`，并确认窗口 PID 属于现有 `vmware.exe`，标题对应 Ubuntu VM。
3. 通过 UI Automation 展开 VMware 的 VM/虚拟机菜单和 Removable Devices/可移动设备子菜单，只选择名称含 `USB download gadget` 的唯一设备，再调用 Connect/连接。若匹配数不是 1，立即退出。
4. 不选择 CH340，不修改“Remember/Always connect”选项，不触碰 VM 设置。
5. 验证 `vmware.log` 新增相同 `path:1/0/4` 的 `Connecting pattern`，随后出现 `ownerdisplay:Ubuntu 22.04 64 位`。
6. 再由来宾执行只读门禁 `lsusb`，要求恰好出现 `18d1:4d00` 和指定序列号，之后才允许现有 RAM-only loader 运行。

该方案调用的是 VMware 自身受支持的连接动作，只把“人工点击”改为可审计的 UI 调用。它不持久化规则，Fastboot 下载结束后 gadget 自动消失属于板端退出 Fastboot 的正常枚举变化。

当前会话不满足第 2 步，故没有尝试连接。

### 方案 B：一次人工菜单连接（当前立即可用）

当板端已经处于 `fastboot usb 1` 且 Windows gadget 状态正常时，用户只需在 VMware 可移动设备中把 `USB download gadget` 连接到 Ubuntu。之后整个 116 MB 传输、CRC、复制与 RAM 启动仍由已有脚本一次完成，不需要在传输中继续点击。

来宾检测到设备后运行的既有入口为：

```text
/home/swl/openvela/work/tts-arena-fix-20260913/load_gated.py transfer
```

该入口调用 `fastboot_ram_download.py`，只实现 Fastboot `download:` 数据阶段；明确没有 flash、erase、boot、continue、reboot 或 OEM 命令。它要求唯一 VID/PID/序列号、116 MB 审计缓冲区、payload SHA256 和 manifest 的 `flash_commands:false`，然后由串口脚本做 CRC、复制和 RAM 启动。

## 不应尝试的路径

- 不再把 `vid:18d1 pid:4d00`、友好名称、物理 path 或 `ehci:0` 传给 `connectNamedDevice`；这不是该命令的对象类型。
- 不调用未公开的 Vigor/VMDB USB RPC。
- 不写 `usb.autoConnect.deviceN`，不设置全局 `usb.generic.pluginAction=GUEST`。
- 不给 `18d1:4d00` 安装或替换 WinUSB/libusbK/Google Fastboot 驱动。
- 不重启 VM、不杀 `vmware-vmx`、不重启 USB Arbitrator 来“刷新”当前正常枚举。
- 不在 Windows 上把 VMware 代理 `0e0f:0001` 当作原始 Fastboot 设备。

## 本轮证据边界

这些结论证明了自动化接口边界和当前主机驱动边界，没有执行热接入，也没有证明 UI Automation 在本会话可用。若后续提供原生 VMware 窗口控制面，先在不传输数据的 Fastboot 空闲状态验证一次“唯一设备连接 + 来宾只读枚举 + 自动退出”，再把它接入主 loader。每次板端 reset 后仍必须重新验证保留的 ASR/TTS 模型 CRC，不能沿用上一次结果。

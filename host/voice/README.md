# Ubuntu 语音唤醒测试窗口

在 Ubuntu 用户桌面运行 `python3 host/voice/launch_panel.py`。使用系统 GTK 3 / PyGObject 和 pyserial；窗口仅为板端串口控制与状态显示，ASR 不在电脑执行。

当前已部署 voice-ui-connect-20260913。`enable_panel.py` 核对该版本 RAM 校验和无线启动日志后开放开始按钮。窗口在用户点击后循环录音、识别、板端 Controller 扫网；只有真实 `WaitingNetworkChoice` 和非空网络列表才判定通过。随后从列表选择网络，在隐藏输入框键入密码并点击连接。`connect-ui` 确认关闭回显后才发送密码；不使用命令参数或原始日志传递凭据。只有板端认证及 DHCP 返回真实 IP 才显示连接成功。互联网、DNS、HTTPS 是后续独立验收项。

停止会等待当前板端命令有界结束，不发送中断破坏推理；串口失败或缺少完整结果会暂停。运行时不要从其他脚本同时打开串口。关闭正在测试的窗口会先请求停止，结束后可再次关闭。

主机测试：`python3 host/voice/test_wake_panel.py`。五组测试通过，覆盖状态、网络列表、IP 和密码回显握手保护。此前 audio-cued 版本真人唤醒与扫网通过；本版本手动配网尚待用户测试。

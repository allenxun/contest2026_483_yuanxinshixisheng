# 正式接入点

候选接口入口为 `include/tool_executor.hpp`：

- MiMo/规则路由层只把受限模型 JSON 交给 `parseModelCall`，不得把完整对话、ASR 密码片段或凭据放进工具 JSON。
- 语音会话协调任务生成 `trusted_request_id` 并串行调用 `Executor`。请求接受、运行、成功、失败、取消和超时应通过真实状态模板送往 TTS；模型不得撰写“拍照成功”“已连接”文案。
- 板端新增一个实现 `ExecutionPort` 的适配器。`start` 只能在请求已复制并由对应服务接纳后返回 true；`poll` 只能返回服务自身的事务结果；`cancel` 保留底层租约直到实际清理完成。

建议接入位置及前置缺口：

1. 网络扫描对接 `app/k7radio/k7_radio_service.h:k7_wifi_scans()` 和 `wifi_scan.h` 的 voice owner 路径。适配器必须保留 service ticket/sequence、离线限制、取消栅栏和最多 8 条结果；不得调用 `k7radio` 命令行或把 scan accepted 当 ready。
2. 状态查询应从共享无线服务新增不可变快照接口，成功字段只能来自真实链路及 DHCP/IP 状态。当前 `k7radio_main.c` 的打印型 `wifi-status` 不是可直接复用的类型化 API，因此本候选不假设它已经存在。
3. 拍照当前入口 `app/k7host/k7host_main.c:camera_capture` 是静态命令实现，并受“一次 capture attempt per boot”等诊断约束。正式工具前应先抽取有 owner、事务 ID、完成/失败事件和保存结果 ID 的相机 mailbox；不能调用 shell 命令，也不能把队列接纳或 JPEG 帧到达当作文件保存成功。
4. VoiceLink 现有 `ports.hpp` 只有 TTS/Wi-Fi/时钟/文字输入，没有通用工具端口。建议在 Controller 外的 Agent 协调层持有本 Executor，避免让 VoiceLink 密码状态机或 `WifiPort` 承担拍照/状态工具语义。

正式迁移门禁应至少包含：目标 ARM64 严格编译；共享服务事件的旧 ID/乱序/取消后迟到注入；真实扫描和状态只读验证；拍照保存 ACK；响应上限；连续释放/复用；设备重启后的事务域隔离。这些均未在本候选中验收。

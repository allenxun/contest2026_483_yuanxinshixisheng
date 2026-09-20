# VoiceLink 主会话接收记录

已接收用户转交的会话 `01a0892e-2964-7ec3-bd76-9ab4937980cb` 的主机候选。暂存目录 `work-in-progress/parallel-voicelink`，未直接应用其补丁，也未修改候选文件。

主会话运行 `tools/verify_voicelink_handoff.py`：17 个交付文件、14 个原输入及其快照、锁定版本的 sherpa 头文件/LICENSE 哈希核对通过；记录的测试报告 passed=true，全部编译/执行退出码为 0，无超时。证据 `evidence/voicelink-handoff-20260910/verification.json`。本次仅复核记录和哈希，没有重复运行已通过的主机测试。正式模型运行库、板端录放音和语音联网尚未验证。

新会话日志已显式加入 `tools/log-sources.json`，首次采集 95 条，归属 `logs/maomaojiang01/`。本次统一原版官方格式校验通过；后续数量以 manifest 为准。格式通过不是比赛验收，也不意味着完整内部过程可导出；脱敏及原生导出限制保持记录。

## 接口核对发现

候选 `WifiPort::beginConnect/pollConnect/cancelConnect` 要求非阻塞、全生命周期唯一事务 ID 和取消只影响本事务。现有 `app/k7radio/prov_wifi.inc` 的 `prov_wifi_connect()` 是持有操作锁的阻塞工作函数，且可主动停止已有网络；BLE 断开后已接受的联网仍继续。这两者不能直接一对一包装，更不能把断开 BLE 当作取消语音事务。

集成时需要抽取共享网络服务，区分 BLE/VoiceLink 请求所有者，分配统一事务 ID，明确排队/忙、取消、超时及成功后网络所有权。IPReady 只能来自真实认证和 DHCP 成功。在线扫描、开放网络等暂不支持能力应明确返回 Unsupported，不回传模拟成功。

## 集成顺序

1. 本会话先完成正在进行的 eMMC RAM 固件只读验证，并恢复无线；不把语音和首次 eMMC 接管混在一个测试版本。
2. 审查候选代码与平台依赖，将独立核心迁入正式应用路径，保留锁定版本和测试证据；旧同步接口平台文件需要重写。
3. 单独实现、测试共享网络事务服务，再接入候选 WifiPort。保持 BLE 原协议的真实状态与事务隔离。
4. 板端音频驱动、sherpa/ONNX Runtime 库和模型路径准备后，先真实 WAV 推理与资源测量，再接麦克风/扬声器和语音流程。

以上步骤尚未全部完成。主机 TTS/ASR fake C API 的成功不表示 NPU 推理或实板语音成功。

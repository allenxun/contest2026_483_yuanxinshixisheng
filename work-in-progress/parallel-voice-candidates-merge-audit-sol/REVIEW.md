# 五个语音候选的合并审查

审查时间：2026-09-12。范围仅为五个候选目录与当前 `app/voicelink`、`app/k7sound`、`app/k7radio`。没有修改正式源码、SDK、设备、VM、串口或中央日志。

## 结论

五个候选不能按任意顺序直接叠加。当前唯一已经进入正式源码的是 `parallel-asr-text-review-sol` 的 `runtime_candidate.cpp`：它与当前 `app/voicelink/src/native_asr_runtime.cpp` 字节相同，SHA256 均为 `a1e7138ecb538a61ea08585d5fecd59e1f7c0a3d134d6fa4d2f3e12cb02fcb41`。候选的 `contract-audit-result.json` 仍记录修改前正式文件 `f611cd...`，因此 `candidate.patch` 已经过时，不能再次应用。

其余四个候选都是主机端契约原型。推荐先补两条底层能力：带代际号的持续 SAI 采集/播放会话，以及接受指定样本、支持协作取消和绝对截止时间的 ASR 入口。之后才能把 capture worker、voice loop 和 prompt adapter 组合起来。Wi-Fi 候选依赖 k7radio 查询快照扩展，应独立完成，最后接回现有 `SharedWifiPort`。

## 冲突矩阵

| 候选 | 当前正式接口 | 直接应用 | 主要冲突或缺口 | 处理 |
| --- | --- | --- | --- | --- |
| ASR text review | `native_asr_runtime.cpp` | 不需要 | 候选实现已经逐字进入正式文件；旧 patch 上下文消失 | 保留现状；只把其边界检查纳入后续指定样本重构 |
| prompt adapter | `TtsPort`、`pio_play_buffer()` | 否 | `TtsPort` 只有动态文本；k7sound 只有每次完整启停的单次播放；没有流式 sink、固定 ID 映射或完整动态提示资产 | 先建持续 TX sink 和结构化 Prompt 接口，再迁入解析/分块逻辑 |
| voice loop | `Controller` | 否 | 没有真实 CapturePort/AsrPort；AsrPort 允许保留 capture 引用，但 timeout/cancel 后 Loop 立即 release，违反候选自己的“ASR 结束后释放”说明 | 修改所有权契约或增加 Cancelling/Draining 阶段，再接 concrete ports |
| Wi-Fi transaction adapter | `SharedWifiPort`、`k7wd_view` | 否 | 候选另造 `TransactionBackend`，正式服务没有对应实现；`k7wd_view` 缺 sequence/认证/DHCP/失败原因；WD_PROGRESS 当前不进入查询快照 | 先扩 k7radio 事务事实，再把翻译逻辑内嵌到现有 SharedWifiPort，避免双层 WifiPort |
| capture ASR worker | `k7sound_copy_mono()`、`k7_asr_microphone_text()` | 否 | 当前音频只有“最后一次全局录音”，没有 capture ID/完成事件；legacy backend 忽略 worker 已复制样本，再次读取全局录音；取消仅协作，析构可无限等非协作后端 | 先补指定样本 ASR 和带代际快照，再把 worker 改为 NuttX/pthread 固定资源实现 |

候选间的关键关系：voice loop 与 worker 可以组合，但必须让 `AsrPort::begin()` 在返回 Accepted 前复制/取得独立样本所有权，或者让 Loop 等待取消清理确认后再释放 capture。prompt adapter 与 loop 只有在 `speak()` 明确表示“播放已经结束”时才兼容；若播放异步，Loop 会立即开麦并录到自身提示音。Wi-Fi adapter 在 `WifiPort` 表面与 loop 兼容，但其 backend 尚不存在。

## 不能直接应用的具体原因

### ASR text review

正式实现已经包含 errno 保留、48000 帧上限、输出有界扫描和 mutex errno 的修正。再次应用 `candidate.patch` 会失败或重复修改。仍需修正其 `frames == 0` 当前返回 `-EOVERFLOW` 的语义；指定样本入口建议返回 `-ENODATA`，超上限才返回 `-EOVERFLOW`。

### voice loop

`Loop::tick()` 在 ASR 超时时调用 `asr_.cancel()`，随后立即 `releaseCapture()`；析构和显式 cancel 也这样做。接口注释允许 ASR 持有 capture 的安全引用，而且 `cancel()` 没有定义为 quiescence fence，因此异步后端可能继续读已经释放或复用的录音。主机假 Asr 不读取 capture，所以 103 项检查没有覆盖此风险。

最小修法二选一。推荐让 concrete AsrPort 在 `begin()` 内把 capture 快照复制进 worker 自有槽，Accepted 即完成所有权转移，Loop 随后可以释放 capture；否则给 AsrPort 增加 `release/drained` 终态并给 Loop 增加 `CancellingAsr` 阶段，直到确认 ASR 不再引用录音后才 release。

此外，正式 `TtsPort::speak()` 没有说明同步完成。如果板载实现只入队就返回，Loop 会在 Controller 返回可听状态后立即开始下一次 capture。集成前必须规定 speak 同步播放完毕，或暴露 prompt transaction 并让 Loop 等待播放终态。

### capture ASR worker

`LegacyMicrophoneTextBackend` 只是兼容演示：它完全忽略 `samples/frames`，调用 `k7_asr_microphone_text()` 再读一次全局录音。连续采集时会把 generation 和实际音频错配。`K7SoundCaptureSource` 同样没有 capture ID，只能读当前最后一段。两者都不能进入正式连续路径。

worker 的双槽与 8 项结果 FIFO 是合理有界策略，但需要明确上游 Busy 时丢弃哪一轮，并把 `droppedResults()` 纳入观测。第三方推理不检查 token 时，取消、超时和析构都不能及时完成；真机实现必须在模型创建前、每个 AcceptWaveform、每轮 ready/decode 和取结果前检查取消/截止时间。

### prompt adapter

现有 `pio_play_buffer()` 一次调用完成 prepare、搬运、stop、amp-off 和恢复。把每个 256 帧块分别传给它会每 16 ms 停启，产生间隙与爆音。22 个 WAV 中还有超过 48000 帧的提示，不能作为单次现有 API 输入。

适配器只验证 PCM 格式、声道、采样率和位深，合入前还应验证 `block_align == 2`、`byte_rate == 32000`、RIFF/data 大小上限，避免异常资源造成超长读取。它只接受 prompt ID，而 Controller 当前发送动态文本；SSID、IP、序号和密码长度提示无法可靠用精确文本映射覆盖。

### Wi-Fi transaction adapter

当前正式边界已经做到 CredentialsReceived 不等于联网完成，并只在 held、合法 IP 的 `WB_IP_READY` 上完成。但 `k7wd_view` 只有 ticket/phase/status/held/IP；`WD_PROGRESS` 被队列接收后不更新可查询状态；`rb_post_connect()` 仍以 `success` 代填 `done.dhcp`。因此候选严格 Snapshot 无真实数据源。

第一轮不要把整个 `WifiTransactionAdapter` 套在 `SharedWifiPort` 外。保留现有扫描和 dispatcher owner，把 sequence、阶段、认证、DHCP、失败原因等字段加到 `k7wd_view`，再复用候选的 translate 规则。这也避免两个 active_id/cancelled_id 状态机叠加。

## 推荐依赖顺序

1. 冻结并核对当前输入哈希；确认 ASR review 修正已在正式 runtime，删除“待应用”假设。
2. 在 k7sound 增加唯一 owner 的持续 voice session：一次初始化 codec/SAI，持续 RX 环形缓冲，带 generation 的不可变 utterance 快照，以及同会话的持续 TX begin/write/finish/abort。
3. 在 ASR runtime 增加指定样本入口，保留现有 microphone 命令为“copy snapshot 后调用指定样本”的诊断包装。
4. 修改 capture worker，删除正式路径中的 Legacy backend，接指定样本入口；完成 NuttX pthread/栈/优先级/模型池释放验证。
5. 修正 voice loop 的所有权与 prompt 完成门，再接 CapturePort/AsrPort；复跑正式 Controller 测试和候选测试。
6. 接 prompt 资源、结构化 ID/参数和持续 TX sink；先固定通用提示，再补数字、SSID 选择和成功详情策略。
7. 独立扩 k7radio 事务快照和真实认证/DHCP/失败原因发布，最后更新现有 SharedWifiPort 翻译。
8. 新增正式 `voice-run` 命令和构建项；按主机 O0/O2、ARM64 编译、ELF、独立 RAM 固件、真机逐层验收。硬件步骤不属于本审查。

## 逐文件最小合并方案

| 文件 | 最小变更 |
| --- | --- |
| `app/k7sound/voice_stream.h`（新） | 声明 session、RX generation/snapshot、TX stream、abort/release；所有 ID 生命周期内不复用 |
| `app/k7sound/voice_stream.c`（新） | 单 owner task、持续 SAI RX 环形缓冲、任务上下文完成事件、不可变双快照、TX 连续短写；任何失败保留 held/fault |
| `app/k7sound/pio.h/.c` | 抽出不会每块 stop 的 begin/pump/finish 原语；保留现有 `pio_play_buffer()` 行为和诊断入口 |
| `app/k7sound/k7sound_main.c` | 只接 voice stream service/诊断；不让 worker 从 ISR 或持有 owner 时回调 ASR |
| `app/k7sound/CMakeLists.txt`、`Makefile`、`Make.defs`、`Kconfig` | 增加 voice stream 可选源和依赖，默认诊断路径不变 |
| `app/voicelink/include/voicelink/asr_runtime.h` | 增加固定 16 kHz float 样本请求结构、绝对单调 deadline、非阻塞 cancel callback、输出契约 |
| `app/voicelink/src/native_asr_runtime.cpp` | 把现有 recognize 拆成 samples 核心；microphone wrapper 只负责 copy；每个长阶段检查 cancel/deadline；保留 RAII/TLS/gate |
| `app/voicelink/include/voicelink/voice_loop.hpp`（新） | 从候选迁入，但收紧 AsrPort Accepted 前必须取得独立样本所有权，或增加 drained API |
| `app/voicelink/src/voice_loop.cpp`（新） | 从候选迁入并修取消释放顺序、prompt 完成门和超时竞态 |
| `app/voicelink/src/capture_asr_worker.*`（新） | 从候选迁入双槽/代际/FIFO；替换 std::thread 层并删除 Legacy backend 正式使用 |
| `app/voicelink/src/voice_prompt_adapter.*`（新） | 迁入 WAV/分块逻辑，补 WAV 一致性和资源大小上限 |
| `app/voicelink/include/voicelink/ports.hpp` | 将动态字符串 TTS 扩为结构化 Prompt ID + 参数，或明确提供同步完成事务；禁止隐式文本匹配 |
| `app/voicelink/src/core.cpp` | 只把提示调用改为结构化事件；规则状态机、密码确认门和 Wi-Fi 完成门保持不变 |
| `app/k7radio/wifi_dispatch.h/.c` | 扩 `k7wd_view` 事务事实与 sequence；PROGRESS 单调更新，COMPLETION 保留释放栅栏 |
| `app/k7radio/radio_backend_state.inc` | 在退出 `rb_lock` 后发布同 ticket Authenticated 事实 |
| `app/k7radio/wifi_ip_service.inc` | 将 DHCP/IP 绑定当前事务并发布 Dhcp 事实，禁止全局旧 IP 完成新事务 |
| `app/k7radio/radio_backend.inc` | 不再用 success 代填 DHCP；保留 join/清理栅栏并映射真实失败原因 |
| `app/voicelink/src/voice_wifi_adapter.cpp` | 在现有 SharedWifiPort 内翻译扩展快照；扫描逻辑不改，不新增第二层 WifiPort |
| `app/voicelink/src/k7voice_main.cpp` | 最后新增长期 `voice-run` 驱动；现有 probe/flow-scan/flow-mic-wake 保留为诊断 |
| `app/voicelink/CMakeLists.txt`、`Kconfig`、`tests/test_flow.cpp` | 分项开关、链接缺口门禁、取消 drain/自声录入/旧 generation/动态提示/Wi-Fi progress 回归 |

## 所需接口

`required-interfaces.md` 给出建议契约。关键要求是：capture ID 必须绑定不可变样本；ASR 必须接受这份指定样本；取消只在后端不再访问样本后才能释放；持续 SAI session 不能每 16 ms 停启；提示播放结束与下一次录音之间必须有明确栅栏。

## 验证结果与边界

`reproduce.ps1` 只把产物写入本目录。当前正式 ASR runtime、prompt、loop、Wi-Fi transaction 和 capture worker 均在 O0/O2、`-Wall -Wextra -Werror -pedantic` 下重编并执行通过。原始输出在 `raw/`，逐文件哈希在 `raw-manifest.json`；全部候选非 exe 文件与选定正式输入哈希在 `input-manifest.json`。

这些结果只证明 Windows 主机假后端契约，不能证明 ARM64、真实 SAI、模型运行、提示音、真实 Wi-Fi、取消清理或完整语音配网。未生成组合正式补丁，因为四个未合入候选的前置接口尚不存在，硬拼 patch 会把已知所有权错误和虚假 backend 一起带入正式树。

# 连续录音到异步 ASR worker 候选

此目录是主机可测的生命周期候选，不是正式 `app/` 集成。它解决的边界是：采集完成线程只复制一份有代际号的单声道快照并入队，模型创建、解码和文本生成全部在专用 worker 中执行。

## 接口与所有权

`Worker::captureCompleted(generation, timeout, source)` 在调用线程执行一次 `CaptureSource::copyMono`，把数据复制进 worker 预分配的缓冲区。函数返回 `Accepted` 后，缓冲区只由 worker 持有，直到后端返回。调用方可以立即复用或改写原采集缓冲。两个固定槽最多容纳一个运行任务和一个待处理快照；再来的录音返回 `Busy/-EBUSY`，不会覆盖尚未释放的音频。

代际号必须严格递增。新录音会取消更旧的运行或排队任务，旧后端即使晚返回也只能产生带原代际号的 `Cancelled`，不会被发布为新录音的文本。`cancelThrough()` 可取消指定代际及以前任务；`poll()` 返回带代际号的终态。终态 FIFO 固定为 8 项，消费太慢时丢最旧项并通过 `droppedResults()` 暴露计数。

超时和取消是协作式的。`Backend::recognize` 必须在模型初始化、分块送样和 decode 循环中检查 `Cancellation`。超时会使该代际终态成为 `TimedOut`。无法检查 token 的第三方调用不能被安全强杀；它返回前仍占用运行槽，析构也必须等待它释放样本和模型资源。

## 现有契约复用及限制

- `K7SoundCaptureSource` 原样调用正式的 `k7sound_copy_mono(float *, unsigned, unsigned *)`。正式实现会尝试取得音频 owner 锁，只复制 `capture_usable` 的最近完整录音，并返回 `-EBUSY/-EIO/-ENOSPC`。它没有录音序号，因而必须由“录音完成”事件在下一轮采集改写缓冲之前立刻调用；本候选的 generation 由上层事件提供。
- `LegacyMicrophoneTextBackend` 原样调用 `k7_asr_microphone_text(char *, size_t)`，只用于证明旧 ABI 能放到 worker 线程。这个函数会在 worker 实际运行时再次调用 `k7sound_copy_mono`，忽略已经绑定 generation 的快照；它还只在整次识别入口做互斥，内部 180 秒预算没有外部取消 token。因此它不能作为连续录音正式后端。
- 正式接入需要从 `native_asr_runtime.cpp::recognize` 拆出类似 `k7_asr_audio_text(const float *, unsigned, cancel/deadline, char *, size_t)` 的指定样本入口。该入口应复用现有 Sherpa 配置、TLS 自检、资源析构和单实例 gate，并在 recognizer 创建前、每次 `AcceptWaveform`、每轮 ready/decode 以及取结果前检查取消与绝对截止时间。

## 正式接入点

1. `app/k7sound/k7sound_main.c` 的采集成功分支在设置 `capture_usable/captured_frames` 后发出完成事件；事件所有者分配严格递增 generation，再通过 `K7SoundCaptureSource` 立即复制快照。不要从 ISR 调用，也不要在持有现有 `owner` 锁时调用。
2. `app/voicelink/src/native_asr_runtime.cpp` 增加指定样本且可协作取消的后端入口；保留 `k7_asr_microphone_text` 作为命令行诊断包装。
3. `app/voicelink/src/k7voice_main.cpp` 或后续 Controller adapter 只轮询带 generation 的结果，并仅把当前期望代际的 `Completed` 文本交给 `Controller::ingest`。Controller 状态切换时调用 `cancelThrough`。
4. NuttX 移植时可将 `std::thread/mutex/condition_variable` 机械替换为 `pthread` 原语；固定双槽、结果上限、所有权及终态规则保持不变。

## 主机复现

在 `E:\openvela\VelaVision` 执行：

```powershell
powershell -ExecutionPolicy Bypass -File work-in-progress/parallel-capture-asr-worker-sol/run_tests.ps1
```

脚本使用 MinGW `g++`，以 O0 和 O2、`-Wall -Wextra -Werror` 分别编译并运行假采集/假 ASR 后端测试。原始标准输出保存在 `results/O0.txt` 和 `results/O2.txt`。

## 尚未完成的真机项

候选没有编入 ARM64/NuttX 固件，未连接真实采集完成事件，未对真实 Sherpa 解码增加逐阶段取消检查，也未验证板端线程栈、调度优先级、模型池峰值、取消后的释放归零、连续录音丢弃策略和 Controller 文本提交。没有实现完整 Controller、提示音或 Wi-Fi 事务，也没有操作设备、串口、SDK 或中央日志。

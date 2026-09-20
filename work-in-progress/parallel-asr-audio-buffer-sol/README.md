# 指定 PCM 样本 ASR 候选

此目录是 `app/voicelink` 的最小候选 overlay，只做主机假 Sherpa 验证，未修改正式源码。`include/voicelink/asr_runtime.h` 和 `src/native_asr_runtime.cpp` 是候选接入文件。

## 接口契约

`k7_asr_audio_text(request, out, capacity)` 在调用期间只读 `samples[0..frames)`，返回前不再保留 samples、回调上下文或输出指针。第一版只接受 16 kHz、1..48000 个 float 单声道帧。`deadline_ms` 是 `CLOCK_MONOTONIC` 绝对毫秒；0 表示只使用内部 180 秒上限。取消回调可为空，否则必须非阻塞且线程安全。

失败返回负 errno 并在可写 capacity 非零时清空输出：`-ENODATA` 表示空样本或空结果，`-EOVERFLOW` 表示帧数超过 48000，`-EINVAL` 表示指针、容量或采样率无效，`-EBUSY` 表示另一个识别占用单实例 gate，`-ECANCELED/-ETIMEDOUT` 表示协作取消/截止，`-ENOSPC` 表示文本缓冲不足，`-ENOMEM/-EIO` 表示资源或运行库错误。

入口在 TLS 自检和模型创建前后、每次送样前、每轮 ready/decode 前后、取结果前检查取消与截止。第三方单个创建/解码调用本身无法安全强杀；回调只能在其返回后被观察。

兼容 `k7_asr_microphone_text` 只调用一次 `k7sound_copy_mono`，再把这份局部快照交给指定样本入口。因此 worker 应直接调用 `k7_asr_audio_text`，不再通过兼容包装重读全局最近录音。

## 复现

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File work-in-progress/parallel-asr-audio-buffer-sol/run_tests.ps1
```

脚本用 MinGW g++ 在 O0/O2、`-Wall -Wextra -Werror` 下编译，并保存原始构建和测试输出到 `results/`。

## 接入顺序

1. 用候选 header/source 修改正式 `app/voicelink` 对应文件并完成 ARM64 编译。
2. 将 `parallel-capture-asr-worker-sol` 的真实 Backend 从 `k7_asr_microphone_text` 改为 `k7_asr_audio_text`，把 worker 的 Cancellation 映射到回调和绝对截止时间。
3. 采集完成事件立即复制带 generation 的不可变快照到 worker 双槽；只发布 request ID 与 capture generation 都匹配的文本。
4. 完成板端资源、取消和 Controller 联调后，才替换诊断命令路径。

## 真机未完成项

尚未 ARM64 编译或编入固件；未运行真实 Sherpa 模型；未验证板端模型池峰值与每条失败路径释放归零；未验证取消/截止延迟、连续双槽、线程栈和调度；未连接真实 capture generation、Controller 或密码清零；未进行麦克风准确率、长期运行或语音配网验收。未操作 SDK、设备、VM、串口、无线、中央日志或远程仓库。

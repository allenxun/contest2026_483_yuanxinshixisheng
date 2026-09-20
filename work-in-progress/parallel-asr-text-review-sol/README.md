# ASR 文本桥独立审查（sol）

范围仅为正式 `native_asr_runtime.cpp`、`asr_runtime.h`、`k7voice_main.cpp` 和直接构建契约。没有修改正式源码、SDK、设备、串口、VM 或中央日志。

## 发现

1. **中：采集后端的 errno 被折叠为 `-EIO`。** `native_asr_runtime.cpp` 在 `k7sound_copy_mono()` 返回任何错误时抛出 `runtime_error`，随后统一捕获成 `-EIO`。正式 `k7sound_copy_mono()` 明确会返回 `-EBUSY`、`-ENOSPC`、`-EINVAL` 和 `-EIO`；当前桥因此不能让上层区分“采集资源正忙，可重试”和推理/设备故障。假实现用 `-EBUSY` 输入稳定复现正式代码返回 `-EIO`，O0/O2 相同。

2. **中：桥无条件信任跨组件返回的 `frames`。** 桥分配 48000 个 float，却没有在 `k7sound_copy_mono()` 成功后检查 `frames <= 48000`。当前正式音频实现自身限制为 48000，因此现版组合路径安全；但这个上限没有进入共享头文件或 ASR API 契约。音频实现回归、替换或假后端只要错误返回更大帧数，ASR 循环就会越过 `recorded` 末尾读取。候选在消费前拒绝 0 或超上限帧数并返回 `-EOVERFLOW`。

3. **低：输出复制先对第三方结果执行无界 `strlen()`。** Sherpa 正常实现应返回 NUL 结尾文本，所以正常路径没有问题；但桥的目标是 256 字节有界输出，当前仍会在异常/ABI 损坏的结果上持续读到任意远处。候选只在调用方容量内寻找终止符，超过容量直接 `-ENOSPC`。

4. **中（构建追溯）：CMake 链接的是外部 `runtime.o`，并不编译正式 `native_asr_runtime.cpp`。** 对象 SHA256 检查能防止传输后变化，但哈希值也由配置者同次提供，CMake 本身无法证明对象来自当前正式源码。配套 `build.py` 用输入哈希补这条链，但它通过字符串替换旧 `recognizer_probe.cpp.o`，没有断言旧对象确实出现且只出现一次；先前链接命令一旦改名，脚本可能静默生成仍含旧入口的对象。审查时 Windows 工作区还没有该构建的 `result.json` 或 `evidence/build/voice-asr-text-20260912`，因此只能确认输入哈希锁定，不能确认这版文本桥已经构建或上板。

5. **低：命令帮助无条件列出可选 ASR 命令。** `flow-mic-wake`、`asr-model`、`asr-mic` 的实现受构建宏控制，但 usage 文本始终列出它们。未启用 ASR 的普通 `k7voice` 会宣传随后必定失败为 usage 的命令，容易误判能力。Kconfig 帮助仍写着 ASR/TTS 未集成，与显式外部运行时选项并存，也应在正式收口时更新。

## 已确认正确的性质

- `Handles` 按 result → stream → recognizer 顺序释放，输出过长、异常和成功均走 RAII；假实现计数验证成功与 `-ENOSPC` 路径各释放一次。
- 入口先清空非空输出缓冲，参数不匹配返回 `-EINVAL`；候选保持该行为。
- 静态 ASR mutex 在成功、错误和异常路径由栈对象释放；O0/O2 双线程假实现验证并发第二次调用返回 `-EBUSY`，首调用完成后门可继续使用。
- 正式 `k7sound_copy_mono()` 在自己的 mutex 下从完成快照转换数据，并检查当前 `captured_frames <= 48000`。现有组合没有观察到共享缓冲竞态。
- CMake 已强制 microphone ASR 同时需要 model runtime 与 `CONFIG_EXAMPLES_K7SOUND`，也用目标引用在缺少所需 ASR 符号时触发最终链接失败。

## 候选与测试

`candidate.patch` 是最小正式源码候选；`runtime_candidate.cpp` 是可直接运行假实现测试的等价完整副本。候选保留音频 errno、校验帧数、精确返回 mutex 错误，并把文本扫描限制在输出容量。

复现：

```powershell
Set-Location E:\openvela\VelaVision
& .\work-in-progress\parallel-asr-text-review-sol\run_tests.ps1
python .\work-in-progress\parallel-asr-text-review-sol\audit_contract.py
```

原始结果为 `baseline-O0-result.txt`、`baseline-O2-result.txt`、`candidate-O0-result.txt`、`candidate-O2-result.txt` 与 `contract-audit-result.json`。测试只使用 Windows 主机假 Sherpa/音频后端，不代表 ARM64 编译、真实模型推理、麦克风准确率、Controller 完整循环或真机验收。

## 未完成项

- 候选没有同步到 SDK、执行 ARM64 编译或生成固件；该操作超出本审查目录权限。
- 没有真机执行 `flow-mic-wake`，也没有接续选网、密码、提示音或配网完整循环。
- 没有对第三方 Sherpa 内部内存安全作独立审计；这里只验证桥的可控边界和假 ABI。
- `k7voice_main.cpp` 的异常隔离和日志转义可进一步加固，但不是这份最小补丁的一部分。

# 多轮语音规则配网编排候选

这是独立待集成候选，只增加录音、ASR 与正式 `voicelink::Controller` 之间的编排层。它不修改正式源码，不实现或复制 ASR runtime、固定提示播放、Wi-Fi 扫描或连接逻辑。

完整顺序是：按 Controller 当前 grammar 开始一轮录音；录音端封存不可变句柄；ASR 端消费句柄并返回 UTF-8 文本；候选立即调用 `Controller::ingest()` 并清零本地文本；Controller 通过现有 `WifiPort` 执行扫描、SSID 选择、密码规则输入、显式确认和连接事务；扫描或连接进行时只调用 `Controller::poll()`，不抢录下一句；Controller 回到可听取状态后开始下一轮录音；成功、取消或错误后停止。

`include/voice_loop.hpp` 是集成接口，`src/voice_loop.cpp` 是实现，`tests/test_voice_loop.cpp` 使用假录音、假 ASR、假共享 Wi-Fi 端口覆盖多轮流程。候选不记录识别文本；密码轮文本仅存在于 `AsrResult` 的局部对象，作用域退出时按字节覆盖。正式 Controller 仍只播报密码长度，不播报密码内容。

在 PowerShell 中复现：

```powershell
cd E:\openvela
& VelaVision\work-in-progress\parallel-voice-loop-sol\scripts\run_tests.ps1
& VelaVision\work-in-progress\parallel-voice-loop-sol\scripts\package.ps1
```

测试以 MinGW g++ 的 `-O0` 和 `-O2`、C++17、`-Wall -Wextra -Werror -pedantic` 编译候选，并直接链接正式 `app/voicelink/src/core.cpp` 和 `parsers.cpp`。每次原始构建/测试输出及 `results.json` 保存到新的 `evidence/run-<UTC>/`，不会覆盖旧结果。

当前只完成主机假端口验证。尚未完成真机连续录音入口、`k7_asr_microphone_text()` 的异步工作任务适配、板载固定提示播放、真实共享扫描/连接联合运行、开放网络真机连接、取消与超时真机清理、长期多轮和重密钥验证。音频质量与 ASR 准确率问题不由本候选修复。

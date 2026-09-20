# VoiceLink Windows CPU 实库验证交接

已完成真实模型检查、官方工具推理，以及上一候选C++代码链接官方实库后的TTS/ASR验证。未改旧交付、模型原文件、正式源码、中央日志或SDK；无硬件操作、云推理或资料上传。

会话ID `01a0892e-2964-7ec3-bd76-9ab4937980cb`，会话cwd `E:\openvela`；唯一新增目录及测试cwd `E:\openvela\VelaVision\work-in-progress\parallel-voicelink-runtime`。目录内.venv仅用于ONNX结构检查和进程测量，不是sherpa Python推理；真实推理由官方exe和官方C API DLL执行。

## 实测结果

| 层次 | 实际结果 | 时间/进程内存 |
| --- | --- | --- |
| 官方TTS exe | 文本“你好，欢迎使用语音助手。”生成 evidence/tts-cli.wav，8000Hz/单声道/PCM16，26443帧、3.305375秒 | 全进程3.473秒，工具报告生成0.206秒；采样峰值RSS 311459840字节、private 303878144字节 |
| 官方流式ASR exe | INT8 encoder/decoder加载并对原test_wavs/0.wav推理，退出0 | 全进程3.274秒；工具报告推理0.57秒；RSS 550662144、private 792666112字节 |
| 上一候选C++实库链接 | 原parallel-voicelink/src/audio.cpp未改动，MinGW g++12.2.0直接链接官方sherpa-onnx-c-api.lib，调用真实DLL。TTS生成evidence/tts-binding.wav，8000Hz/PCM16、35328帧、4.416秒；ASR对相同原WAV输出文本，关闭释放后退出0 | 两模型加载5.961秒，TTS .164秒，ASR .510秒，全进程6.983秒；采样峰值RSS 812953600、private 1026174976字节（约978.6MiB） |

官方ASR实际输出：`昨天是 monday tedis is 礼拜二 the day after tomorrow 是星期`。

候选binding实际输出：`昨天是 monday today day is 礼拜二 the day after tomorrow 是星期`。

两者文本有差异，且存在英语识别错误/尾句不完整；保留真实输出，不声称识别准确率通过。没有使用fake C API。候选binding证明Windows C API ABI/链接和本次模型路径可运行，不证明NuttX链接、音频设备、全语音状态机或长期资源无泄漏。

所有推理为CPU、num_threads=1。内存通过psutil6.1.1每20ms采样子进程memory_info，记录RSS、private及Windows报告的peak_wset；采样可能漏过瞬时峰值，进程包含库/堆/模型/缓存，不能当成模型独占内存。Windows约979MiB private峰值不能推导为板端1GiB池足够或不足，板端ORT编译、分配器和线程配置须另测。

对应完整命令/退出码/耗时/内存、stdout/stderr原始字节：

- evidence/tts-cli-20260910T032007632390Z/result.json
- evidence/asr-cli-20260910T032011222176Z/result.json
- evidence/cpp-binding-20260910T032131279150Z/result.json

stderr混合了Windows本地代码页的路径和UTF-8识别文本，UTF-8查看版本中部分路径显示替换字符；原始.raw文件完整保留。模型绝对路径在models.json中是有效UTF-8。

## 复现

当前目录依赖已落地：官方v1.12.14解压在runtime/；.venv为本机已有Python3.12.14创建，ONNX/psutil及传递依赖准确版本在evidence/requirements-lock.txt。没有全局安装。新环境先从MODELS.md官方URL下载同资产并核对SHA-256，建立本地venv后 `python -m pip install -r evidence/requirements-lock.txt`；原模型按models.json路径提供并核对哈希。保留原模型只读，不需要模型拷贝。

```powershell
Set-Location -LiteralPath 'E:\openvela\VelaVision\work-in-progress\parallel-voicelink-runtime'
./build_binding.ps1
./.venv/Scripts/python.exe scripts/run_measured.py cpp-binding ./real_binding.exe 'E:\openvela\语音模块\openvela-voicelink\models' 'E:\openvela\语音模块\openvela-voicelink\models\sherpa-onnx-streaming-paraformer-bilingual-zh-en\test_wavs\0.wav' 'evidence/tts-binding-rerun.wav'
```

build_binding.ps1只读引用上一候选头文件和audio.cpp，不修改它们；运行时PATH仅对子进程加入官方DLL目录。用对应result.json的command数组可复现官方exe调用，建议更换输出WAV路径保留旧证据。scripts/inspect_models.py可重新检查原模型结构并生成清单。

## 失败及边界

最初系统python/py实际指向Python3.6，`py -0p`不是Windows launcher命令而失败。查询 `https://pypi.org/pypi/sherpa-onnx/1.12.14/json` 返回404；未因此换版本，而是直接采用同版本官方Windows release（确有TTS及C API库）。不能据一次404推断不存在其他发布渠道的Windows wheel。

首次TTS真实exe已产生WAV，但测量脚本打印混合编码时UnicodeEncodeError，未写result.json；该轮残留.raw保留在更早的tts-cli目录，不计入完整测量通过。修复脚本stdout编码后重跑，以上表格来自完整报告。首次WAV被重跑覆盖，交付仅声明最终保留产物。失败摘要为实际事件记录，不伪造原stderr或运行结果。

模型结构/config见MODELS.md。下一步由主会话处理8kHz输出与真实codec配置、ORT1.17.1/sherpa1.12.14目标工具链和库依赖、NuttX内存分配接入、实际音频录放及长稳、ASR尾部flush/准确率和时延预算。此会话中央日志源已由主会话登记，继续统一采集/官方校验，本轮未改中央日志。

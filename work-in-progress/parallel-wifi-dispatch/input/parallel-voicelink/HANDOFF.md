# VoiceLink 主机端交接

2026-09-10：已完成主机候选实现、可复现测试和接口审查，尚未集成到正式固件。

## 实际范围

- 会话 ID：`01a0892e-2964-7ec3-bd76-9ab4937980cb`，来自运行环境 CODEX_THREAD_ID / CODEX_SESSION_ID。
- 会话工作目录：`E:\openvela`。所有开发输出：`E:\openvela\VelaVision\work-in-progress\parallel-voicelink`；测试进程工作目录也是此暂存目录。
- 原模块：`E:\openvela\语音模块\openvela-voicelink`，只读；未复制 models、build 或私密配置。
- 未使用板子、COM8、蓝牙适配器、Ubuntu/SDK、U盘、执行机构；无同步、刷写、提交或推送。没有修改正式源码或中央日志。

## 变更清单

| 文件 | 内容 |
| --- | --- |
| include/voicelink/types.hpp、ports.hpp、controller.hpp；src/core.cpp | 从输入演进出异步联网状态机；事务隔离、独立超时、取消及密码清理；去掉同步 Ok 成功接口。 |
| include/voicelink/audio.hpp；src/audio.cpp | PCM16转换、短写输出、sherpa v1.12.14接口适配、流式解码与 RAII 资源释放。 |
| src/parsers.cpp；include/voicelink/parsers.hpp | 原样保留解析器。 |
| tests/test_async.cpp | 42个主机模拟场景（含9个TTS异常清理场景）：接收、进行中、IP成功、失败/忙/不支持/取消、超时边界、旧事务、密码清理等。 |
| tests/test_audio.cpp | 23个主机场景，使用官方头文件+自行实现的 fake C API；包含全部65,536个PCM16值的往返检查、奇数短写、非法输出、初始化失败、解码预算和析构。 |
| input/、evidence/inputs.json | 14个选定输入快照、原路径和哈希；不修改/应用回原模块。 |
| vendor/sherpa-onnx/ | 固定提交的官方头文件、LICENSE、version-lock.json；没有库或模型。 |
| prepare_candidate.py | 从 input 重建候选网络核心的确定性本地脚本，不生成音频或测试文件。后续人工修改核心时需同步更新或停止使用该脚本。 |
| run_tests.py | 在独立时间戳目录编译执行；保存原始输出、超时/失败状态、运行前后源码哈希；先前轮次不覆盖。 |
| package_delivery.py | 核对通过报告、测试源码与官方头文件锁定哈希后生成评审补丁和交付清单；拒绝未测试的源码变更。 |
| candidate.patch | 相对原 VoiceLink 根目录的评审补丁，包含修改核心、新音频和新测试；不含平台集成，勿直接应用至主项目根。编译音频需同时携带 vendor/ 并添加 -Ivendor。 |
| 接口与审查.md | 完整接口约束、版本来源、音频审查与未完成项。 |

## 复现及结果

Windows PowerShell：

```powershell
Set-Location -LiteralPath 'E:\openvela\VelaVision\work-in-progress\parallel-voicelink'
python -u run_tests.py --compiler 'D:\software\mingw64\mingw64\bin\g++.exe'
```

Python 3.6+标准库、C++17编译器即可，不需要 CMake、网络、SDK 或任何设备。脚本给子进程 PATH 加入编译器目录以找到 MinGW 运行库；编译使用 `-O2 -Wall -Wextra -Wpedantic -Werror` 和 UTF-8 源字符集。每个编译/测试子进程限时120秒。当前实际编译器为 MinGW GCC 12.2.0；未进行其他平台或 sanitizer 验收。

最新通过轮次：`evidence/run-20260910T025351082161Z/result.json`，共8个测试可执行文件：原始快照5组、候选网络42项、候选音频23项、候选解析器回归1组。全部编译及执行退出码为0，原输入14个哈希全部未变，测试前后全部源码哈希一致。上一版33项网络测试通过的结果仍保留在 evidence/run-20260910T024748380029Z/。原5组仅证明原基线；候选行为由候选测试单独证明，不能将基线结果算作候选网络测试。

首轮 `evidence/run-20260910T024629041252Z/` 保留了候选测试构建的 `-Werror=misleading-indentation` 失败，修正测试缩进后重跑通过。首次 PowerShell/curl 官方头文件下载因系统 TLS 凭据失败，后用 Python urllib 成功；版本锁核对脚本曾遇 Windows 路径键格式错误，修正后按 commit 成功校验，均不涉及运行固件。

本轮进一步修复：TTS speak/stop 异常不会绕过清理；feed 参数错误、取消或解码预算耗尽会立即释放流，必须 beginStream 开始新一轮。保留官方 C API 模型运行尚未验证的边界。

独立目录复现只依赖 input 快照；脚本核对快照原始哈希，不要求原绝对路径存在。若要同时将原输入漂移作为失败条件，追加 `--input-source 'E:\openvela\语音模块\openvela-voicelink'`。最新实际运行使用了这个严格检查选项。

生成交付材料：

```powershell
python package_delivery.py evidence/run-20260910T025351082161Z/result.json
```

`evidence/delivery.json` 指向最新通过报告并记录交付文件哈希；带时间戳清单保留每次重新生成的结果。代码更改后必须先重跑测试，再传入对应新报告。本补丁不含原模块的平台文件或库，不是固件安装包。

## 主会话接手

1. 比较 evidence/inputs.json 与当前原模块输入哈希。用 candidate.patch 与候选源码评审，决定迁入 app/voicelink 等正式位置。正式平台适配器需要迁移，不再兼容旧同步 connect 返回值。
2. 由 k7radio 提供共享事务服务，保持 BLE/语音互斥、非阻塞操作、凭据所有权、真实认证/DHCP事件与取消语义；在线扫描/开放网络仍需明确支持状态。
3. 核对板版 I2S/codec、音频驱动/格式、录放音与有界I/O；固定 sherpa/ONNX Runtime 实际库、工具链、模型和配置，完成链接及真实 WAV 推理、内存峰值、时延测量。本轮只按官方头文件编译并链接测试替身。
4. 由主会话执行 SDK 差异审计、同步、固件编译和独立有界真机验证；本轮没有做这些操作。主机模拟 IP 不是真机配网，资源释放计数不替代实际运行库的泄漏/长稳检查。
5. 最终 AI 日志归属 `VelaVision/logs/maomaojiang01/`。按上面的实际会话 ID 和 cwd 核对自动采集范围/会话纳入情况，再运行原版官方 `tools/official-validator/tools/validate-log.py logs/`。本轮未改中央日志、未手写 JSONL、未运行中央收集器或校验器，**日志已入库及官方校验通过均未确认**。原始会话由 Codex 保存，不复制到本暂存目录。

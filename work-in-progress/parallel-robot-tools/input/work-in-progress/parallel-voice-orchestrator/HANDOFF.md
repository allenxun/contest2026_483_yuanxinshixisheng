# VoiceLink 主机生命周期编排交接

2026-09-10；会话 `01a0892e-2964-7ec3-bd76-9ab4937980cb`，cwd `E:\openvela`。本任务开发输出仅本目录。主会话 `01a07ed4-3f0d-7450-8bb1-bb756849cb4e` 负责审查集成及同仓 `logs/maomaojiang01` 自动采集/原版官方校验；本轮没有写中央日志或手写 JSONL。

已完成主机候选与验证。变更包括 `include/orchestrator.hpp` 的七状态/单事务/截止/取消/迟到结果隔离，`src/audio.cpp` 与头文件的互斥 ASR/TTS 创建，`src/demo.cpp` 的独立工作线程及真实 C API WAV 链路，`include/mock_wifi_task.hpp` 的可替换 TaskPort 模拟例子，模拟故障测试和有界运行脚本。broker 原样复制；输入基线与哈希在 `input/`，基于该基线的补丁是 `candidate.patch`，不基于仓库 HEAD。

最终验证目录 `evidence/run-20260910T035223805472Z/`：

- C++/C 以 Wall/Wextra/Werror 编译成功。模拟编排 10523 个断言、0 失败，覆盖所有阶段故障、正在运行时取消、未确认释放、迟到/重复结果、busy、容量、空文本、ID 耗尽、阶段/总超时与时钟倒退。模拟 broker 覆盖凭据/连接中/IP 成功、失败，以及取消后晚到成功不能释放、退出后仍在线不能释放。
- 真实库分别完成 release、hold 两种资源策略，以及真实 ASR/TTS + 模拟 WiFi TaskPort 三条完整链路，退出码均 0，输出均 mono PCM16/8000 Hz WAV。每次只加载一次 ASR、一次 TTS，日志断言 ASR 完成→释放确认→TTS 加载。默认链路实测 6.468 秒，主机峰值 private 777818112 bytes，20 ms 采样；另外两条 6.282/6.437 秒。不是实时话筒延迟，也不代表板端模型池能容纳。
- 50 ms 请求取消的真实试验退出码 20，实际 2.578 秒才结束，因模型创建是同步调用；无音频文件提交。真实缺模型与缺 WAV 两例均退出码 3。mock 故障与这些真实错误分别留档。
- 自然 WAV 识别原文：`昨天是 monday today day is 礼拜二 the day after tomorrow 是星期三`。默认 TaskPort 固定回答 `你好，已收到语音。`。仅保留实际识别结果，不宣称语义理解/完整转写准确率。

重现命令（每次创建独立 UTC 时间戳目录，子进程上界 60 秒）：

```powershell
& 'E:\openvela\VelaVision\work-in-progress\parallel-voicelink-runtime\.venv\Scripts\python.exe' -X utf8 'E:\openvela\VelaVision\work-in-progress\parallel-voice-orchestrator\scripts\run.py'
```

完整编译/执行 argv、退出码、时长、内存采样及 stdout/stderr 原始字节在上述证据目录。版本记录核对 ORT 1.17.1；C API 头 SHA-256 固定，执行核对 sherpa 1.12.14。模型/动态库输入 SHA 见 runtime-inputs.json；其余模型 sidecar 原始核对来自 runtime 的 models.json，不复制模型全集。

失败记录保留：首次 run 的 MinGW filesystem 对中文窄路径解释与 C API 不一致，读取 WAV 报不存在、退出 3；修改为与 C API 一致的原生窄路径流读取后两轮通过。首次成功轮模拟为 10372 断言；最终增加各阶段故障与总时限覆盖为 10523。脚本最后仅将头文件哈希常量的等价字符串表达式整理为直接常量，未改变执行语义。

接口/线程/同步阻塞/资源策略/Agent 替换详见 CONTRACT.md。板端未完成项：真实录放音驱动与采样率协商、openvela 线程/锁和模型加载器移植、实际内存/时延评估、不可中断驱动恢复、正式 WiFi 服务端口、真实 Agent 服务及其取消/释放确认。未操作任何硬件、SDK、正式源码或旧候选；未提交推送。交接完成后按主会话授权继续独立 `parallel-k7-audio` 准备。

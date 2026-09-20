# 语音收尾和模型常驻内存取舍交接

任务已完成主机实验、有限补尾候选和生命周期建议。新输出仅parallel-voicelink-tuning，既有runtime/voicelink/wifi-service及原模型保持只读；没有硬件、SDK、全局安装、云API或上传操作。

实际会话ID `01a0892e-2964-7ec3-bd76-9ab4937980cb`；会话cwd `E:\openvela`，本轮工作及测试cwd `E:\openvela\VelaVision\work-in-progress\parallel-voicelink-tuning`。

先读FINDINGS.md，再看evidence/memory-table.md、memory-summary.json、delivery.json。核心结论：同一人声样例补300ms尾静音恢复最后一个参考字，额外前补300ms会重现缺字；其他识别误差未消失。提出显式有限补尾API，不改变原通用finish。四种生命周期各3次独立进程，顺序加载显著降低本机进程峰值，但每次重载有数秒成本，不证明板端内存/时延满足要求。

## 交付及证据

- src/probe.cpp：直接链接固定v1.12.14真实C API的流/生命周期探针；无fake。
- src/audio.cpp、include/voicelink/audio.hpp：复制旧候选后新增finishWithTail；原快照在input/candidate/，评审补丁candidate.patch。
- src/candidate_test.cpp：真实模型验证补尾、EOF/取消/预算/释放边界，共1657条断言，failures=0，evidence/candidate-real/。
- scripts/run_suite.py：人声/自合成音频对比和12个独立内存进程；25轮首批运行在evidence/suite-20260910T033126Z/，补充2轮单因素实验在evidence/suite-20260910T033351Z/。每轮command/result/stdout/stderr/raw/memory.csv齐备；测试前期望参考存expectations.json，参考是模型发布结果而非人工真值。
- input/run_suite-v1.py保留第一批运行时脚本；后续脚本仅增加extra选择，不重跑原批次。
- scripts/summarize.py：生成内存表及数值范围；scripts/run_candidate.py为候选重跑入口；build.ps1可编译两个程序。
- 官方源码固定commit下载/哈希在evidence/official-sources.json；输入模型/音频/库/旧候选哈希及交付哈希在evidence/delivery.json，没有复制模型大文件。

复现（复用上一任务已安装的本地Python环境和官方库）：

```powershell
Set-Location -LiteralPath 'E:\openvela\VelaVision\work-in-progress\parallel-voicelink-tuning'
./build.ps1
../parallel-voicelink-runtime/.venv/Scripts/python.exe scripts/run_suite.py
../parallel-voicelink-runtime/.venv/Scripts/python.exe scripts/run_suite.py extra
../parallel-voicelink-runtime/.venv/Scripts/python.exe scripts/run_candidate.py
```

复跑每轮新进程，有60秒执行上限，原证据目录不覆盖。summarize.py默认指向已交付的主实验目录；分析新轮次时需显式更改该只在本目录的路径。C++17/GCC12.2、单线程CPU、Sherpa1.12.14/ORT1.17.1、原INT8模型均未切换。内存结果不是重复原单元测试，是真实库四种生命周期的新实验。

## 保留的失败/不足

首轮probe构建被-Werror的misleading-indentation拦截，真实输出在evidence/build-01.txt、退出码文件；修正后build-02通过。一次PowerShell内嵌字符串编辑发生语法错误，命令未执行，后用结构化补丁完成。第一次汇总因Windows默认GBK读取UTF-8 JSON失败，明确指定UTF-8后成功；没有修改任何推理输出。这两项脚本工具错误可追溯到本真实会话，不伪造额外原始stderr文件。

所有正常探针退出0；cancel=20和budget-zero=21按实验前定义拒绝。整句期望不一致、自然人声未人工核听、自合成文本识别错误、Windows测量限制在FINDINGS.md保留，不能把退出0说成准确率通过。未测试跨模型通用补尾、实际录音endpoint分段、板端存储/音频、真实多线程或长时间泄漏。

主会话接手：核对哈希后选择是否集成finishWithTail及300ms专用模型配置；先在正式语音生命周期中分离ASR/TTS所有权和错误回滚，再做目标库移植、板端峰值/加载时延/录放音验证。现有1GiB专用模型池是否适用仍待实际分配审计；日志继续由主会话按既有登记统一采集，本轮不改中央日志。

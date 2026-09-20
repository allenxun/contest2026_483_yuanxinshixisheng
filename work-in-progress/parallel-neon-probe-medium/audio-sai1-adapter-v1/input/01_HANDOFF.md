# K7 板载/USB 音频准备交接

2026-09-10。会话 `01a0892e-2964-7ec3-bd76-9ab4937980cb`，cwd `E:\openvela`。本任务仅在 `E:\openvela\VelaVision\work-in-progress\parallel-k7-audio` 输出；前一任务 `parallel-voice-orchestrator/HANDOFF.md` 已先完成。主会话可直接读取交接材料，本轮不再请求新任务或跨线程发送。

已完成本阶段可独立进行的准备：

- 核对两版PDF相关页面与官方K7 DTS，确认原理图为ES8388/I2C3 0x10/SAI1 M0；两路功放标替代型号，实板贴装、喇叭负载等保留待确认。供电、引脚、时钟/复位、偏置、连接器、板版差异见 HARDWARE.md，每项有页码或源码路径依据。
- 只从本地官方Git对象库取出14个选定blob，共557790字节，逐一复算Git blob OID并记录SHA-256；没有全量解压或执行Linux脚本。官方库commit `24a411114a2e4e3db89acdf15271aa7a32a8590d`（本地commit.txt）。选取SAI与I2S_TDM作对照：RK3576应追踪rockchip_sai，不能照搬旧TDM寄存器。
- 核对当前overlay/构建config，识别xHCI有通用ISO IN/OUT基础，相机批量API仅IN且不保证批间连续；UAC类层、格式协商与同步反馈仍需实现。板载和USB差距、先录音的最小路径、有界板测建议见 PLAN.md。
- 完成纯主机初始化步骤候选、故障清理状态、PCM16声道/分块适配及有限USB包量规划。12个unittest测试通过，含所有11个初始化步骤故障注入、等待退出/busy/迟到确认、超时、60组PCM分块/声道组合、容量/截断/采样率拒绝、44.1k包分数和不支持同步模式。它们是模拟与算术测试，不是实板驱动测试。

测试命令：

```powershell
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 'E:\openvela\VelaVision\work-in-progress\parallel-k7-audio\scripts\verify.py'
```

真实执行证据：`evidence/run-20260910T040124050804Z/`，result.json含argv、exit=0、30秒进程上界；stdout.raw/stderr.raw保存原始输出；另含项目输入哈希、两版原理图文字diff、带行号的codec原始语句参考。`scripts/extract_sources.py`提取PDF文字/筛选路径，`render_pages.py`生成相关整页图供核对，`extract_blobs.py`执行定点git cat-file并校验OID。渲染使用已安装pypdfium2，无新安装；PDF仅只读。

保留失败/限制：初始探测fitz模块不存在，改用已安装pypdf/pypdfium2；最初脚本名inspect.py遮蔽Python标准库，执行失败后改名extract_sources.py。原始失败在本会话真实工具日志，未伪造原始输出文件。原对象树无独立es8388.c/h；K7 DTS通过everest,es8323兼容串匹配es8323.c，不能把文件名缺失写成驱动必然缺失。参考mute为空实现，多次probe寄存器写未检查错误；因此codec-reference-only.json不可执行。

并发输入变更：最终复核 `port/new/nuttx/arch/arm64/src/rk3576/Kconfig` 与本任务读取快照不一致，新增 RK3576_SMP_DIAG 两核A53诊断选项，见 evidence/concurrent-kconfig.diff/json。音频相关配置结论仍明确针对model-arena快照，不扩展为最新SMP固件结论。原PDF、xHCI及其余抽样输入复核一致；delivery中该项unchanged=false必须保留，主会话集成前重新核对。测试脚本重跑遇到输入变化会写入新run目录，保留首次来源快照。

仍依赖主会话：实板版号/codec及功放装料、麦克风及喇叭规格/负载、实际电压/时钟/引脚冲突，SDK完整树的SAI/DMA/I2C3能力、正式lower-half与构建、DMA停机确认与恢复、真实USB音频描述符、录放音验收。需要时由主会话提供这些证据；未确定项已留在材料中，不妨碍本阶段准备交付。没有访问板子、COM8、蓝牙、U盘、SDK/VM、同步或固件，没有发声或写正式源码，没有提交推送。

日志归属同仓 `logs/maomaojiang01`，请主会话按本会话ID核对自动采集范围及原版官方格式校验。此目录仅保存源码、测试及交接证据，没有手写JSONL，也未改中央日志。`evidence/delivery.json`记录全部交付哈希和输入最终复核；`candidate.patch`仅包含新增纯主机候选及测试，不包含官方blob或PDF全文。

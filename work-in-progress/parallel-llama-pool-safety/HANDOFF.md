# llama / ggml 线程池安全候选交接

本轮委派的软件候选完成；供主会话审查后集成，不是板端验收。实际会话 `01a0892e-2964-7ec3-bd76-9ab4937980cb`，cwd `E:\openvela`，唯一开发输出 `E:\openvela\VelaVision\work-in-progress\parallel-llama-pool-safety`。

基于已交付 B0 的官方固定 `74d4f5b041ad837153b0e90fc864b8290e01d8d5`，7份输入路径/SHA见 input/sources.json。原 parallel-llama-b0 完全只读，复用了其本地CMake3.31.6工具；没有下载源码或权重。源归档、原版LICENSE和派生静态注册表均保留。

实现改变实际 ggml-cpu.c：逐项检查分配/初始化/线程创建结果，停止并join已创建的worker，资源按初始化成功状态释放；清理失败保留指针供重试。新增每池元数据和请求栈预算、线程数上限及诚实的“不支持亲和性”结果。原隐式池路径创建失败返回ALLOC_FAILED。契约、预算不覆盖项和上游更广限制详见 CONTRACT.md。

最终证据 `evidence/run-20260910T063440936377Z/`：GCC/G++12.2，真实编译链接成功；`cases=66 checks=144213 failures=0 real_pthread=1 weights=0 affinity_supported=0`。每个测试进程30秒限时，命令/退出码/耗时见commands.json。

测试覆盖：2/4线程×初始暂停/运行两状态；池/worker两处分配、mutex、cond、attr初始化、stack属性和每一个辅助线程创建故障点；失败后资源归零再创建并运算。额外验证预算少1字节拒绝、恰好额度成功、溢出、mask/strict/priority不支持、创建失败同时join未确认时保留资源并重试、旧API正常创建，以及隐式5线程超默认预算返回失败。

正常计算为64×64张量逐元素乘法，全部4096结果为4；MUL在固定源码中使用多线程任务分配。观察各辅助worker进入实际图计算，检查bitmask并在join后检查实际开始/退出数，避免只把“线程参数=4”当作四线程运算证据。没有模型推理、吞吐率或板端性能结论。

首轮证据 `run-20260910T063319698940Z` 保留，随后补强了实际启动数、strict拒绝和隐式池失败用例；最终以新目录为准。本轮无被隐藏的测试失败，上游编译warning原样保留。没有TSan/全进程泄漏验收。资源归零只覆盖候选跟踪的池/线程/同步对象。

变更/复现入口：CMakeLists.txt、include/ggml-pool-safe.h、candidate/pool-create.inc、pool-destroy.inc、scripts/derive.py、生成的candidate/ggml-cpu.c及pool-safety.patch、tests/pool.c。patch是相对官方CPU源码的改动，另外必须带新增头文件和POSIX编译配置。不能只套patch就声称所有平台支持。

```powershell
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 scripts/derive.py
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 scripts/build.py
# 对新生成的证据目录运行审计；下面是本次交付目录：
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 scripts/audit.py evidence/run-20260910T063440936377Z
```

每次build新建UTC目录：配置90秒、构建180秒、运行30秒，超时终止脚本启动的子进程树。source-manifest与archive-verification核对未修改的官方源码；delivery.json提供交接文件哈希，生成物范围明确。输入前后核对见最终audit.json。

尚待主会话：审查checked API接入、真实NuttX pthread栈/资源预算、C++/TLS平台构建、失败清理监督及CPU亲和性适配。legacy void free在异常清理失败时仍abort，主线应选择checked API；join等待需上层监督，不能超时即free。普通malloc/模型arena/图和KV分配仍待另项，不扩大本轮改造。

没有操作板子/COM8/蓝牙/存储/执行机构/SDK/VM、正式app/port/board、旧交付或中央日志，没有提交推送。实际AI日志请主会话继续采集本会话并用原版官方校验器验证，最终合入同仓logs/maomaojiang01；未手写JSONL。

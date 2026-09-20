# llama.cpp B0 主机准备交接

委派范围完成：固定官方源码、CPU 静态库构建、真实 C API 链接/执行探针、NuttX 依赖表和候选差异均已交付。未下载模型权重、未进行 LLM 推理、未编译 NuttX 固件。下一步应先补 C++平台与线程/内存失败路径，再做模型文件路径。

主任务随后同步：新增正式 app/k7cxx 和 cxx-probe-20260910，正尝试 NuttX ARM64 LLVM libc++/libc++abi 17.0.6、gnu++17、exceptions/RTTI、TLS_NELEM=8，并验证容器、线程/条件变量、steady_clock、posix_memalign 与 RAII 异常清理。此信息来自主任务消息，尚未编译完成或上板；本会话未读取新正式源码或访问 SDK，不将计划视为成功。下文原 smp-load 配置缺口是固定输入版本的事实，不代表新候选必然失败。

- 实际会话 ID：`01a0892e-2964-7ec3-bd76-9ab4937980cb`；cwd `E:\openvela`。
- 唯一输出目录：`E:\openvela\VelaVision\work-in-progress\parallel-llama-b0`。
- 主任务：`01a07ed4-3f0d-7450-8bb1-bb756849cb4e`。正式源码、SDK、硬件和中央日志由主任务处理。
- 版本：ggml-org/llama.cpp b5046，commit `74d4f5b041ad837153b0e90fc864b8290e01d8d5`，来源和许可证见 VERSION.json、PROVENANCE.md，完整原版代码在 vendor。

最终成功证据：`evidence/run-20260910T061731515740Z/`。

| 实测 | 结果与边界 |
| --- | --- |
| GCC/G++ 12.2.0 + CMake 3.31.6，39 编译单元 | 真实编译/链接通过，4 个静态 archive；无 common/server/examples/OpenMP。 |
| 真 CPU backend / pool | 2、4、2、4 线程参数，四次图计算结果均为 16384（4096个2的平方求和）。线程池与 backend/graph buffer/context 成对释放；不是 token 推理或 ARM性能。未测试全覆盖内存泄漏或每核利用率。 |
| 加载错误 | 不存在文件与无效 GGUF 均被真实 llama loader 拒绝，最终 failures=0，weights_loaded=0 / inference_performed=0。没有真实 llama context 或模型，因此未调用模型上下文的线程数 getter 作假验证。 |
| 静态 registry 候选 | CPU 注册数1，动态 load 拒绝、目录扫描关闭；nm 检查 ggml.a 不含动态加载/filesystem 未定义导入。 |
| 主机运行时 | EXE仍导入 libstdc++、libgcc、libwinpthread 及 Windows系统 DLL；“静态库”不表示 EXE 或 NuttX ABI已静态就绪。 |
| 输入复核 | 方案、示例配置、smp-load .config 共3份，在 audit.json 核对时哈希均未变化。 |

初次失败保留在 `evidence/run-20260910T061518577404Z/compile.log`：上游头文件声明但未实现的 ggml_threadpool_get_n_threads 导致链接失败。探针去除此依赖后通过。未隐藏初次错误，也未提供伪造 getter。上游编译器 warning 与源码包无 .git 的版本探测信息原样保留。所有编译/执行命令、返回码、限时和耗时见 commands.json；配置限90秒、构建限300秒、运行限30秒，超时会终止该脚本创建的进程树。

复现命令（PowerShell，在本目录）：

```powershell
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 scripts/build.py
# 使用上一步输出的新证据目录执行审计：
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 scripts/audit.py evidence/run-20260910T061731515740Z
```

已有源码无需再次 prepare。新构建保存在新时间戳目录，必须对新的目录运行 audit；示例中固定目录用于复核本交付。源码获取和候选生成步骤见 PROVENANCE.md。构建可复现指同一固定来源与命令可重新编译/测试，不声称不同绝对路径/工具链产出字节一致。

四个 archive 位置与 SHA 位于最终 audit.json：libllama.a 3,516,102 字节；ggml-base.a 801,932；ggml-cpu.a 595,518；ggml.a 14,676。原始编译命令、CMakeCache、链接响应文件和 EXE 导入表均随证据保留。不能把这些 x86-64 archive 复制进 ARM固件；NuttX必须重编译。

主要阻塞：当前 HAVE_CXX/HAVE_CXXINITIALIZE 未启用；TLS槽配置为0；USB MSC/FAT未启用且没有模型文件路径；1GiB显式arena不接管 malloc/new。固定上游版本线程创建失败会断言、pool分配部分路径未检查空指针，unsupported affinity 返回true而不绑核。详见 DEPENDENCIES.md 各固定源码位置与处理建议。没有添加假 POSIX 成功实现；这些板端问题仍保留。

交付变更仅本目录根 CMake、probe/b0.c、candidate 静态注册表和差异、脚本/文档/证据。vendor 完整来源不修改。source-manifest.json 与 archive-verification.json 核对解包来源；delivery.json 给出可交接文件哈希并说明生成物排除范围。工具安装文件和编译中间文件留在本目录以便复核，独立 inventory 不将其误认作需要集成的正式源码。

本轮没有访问板子/COM8/蓝牙/存储设备/SDK/VM/私密配置，没有修改主项目或任何旧候选，没有提交推送。AI日志最终归同仓 logs/maomaojiang01：请主会话核对自动采集该会话最新记录并使用原版官方校验器验证。本会话不手写 JSONL，也不声称本轮最终中央日志已完成刷新。

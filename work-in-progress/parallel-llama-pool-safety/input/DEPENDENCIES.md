# NuttX / openvela B0 依赖表

表中行号均针对官方固定提交 `74d4f5b041ad837153b0e90fc864b8290e01d8d5`（b5046），本地根为 `vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/`。可对照 [固定提交源码](https://github.com/ggml-org/llama.cpp/tree/74d4f5b041ad837153b0e90fc864b8290e01d8d5)。这是一份基于源码的移植差距表，不是 NuttX 编译通过清单。Windows 主机构建不能覆盖 ARM64、NuttX libc 或实际固件配置。

主任务已通知正在独立 cxx-probe-20260910 尝试 LLVM libc++/libc++abi 17.0.6、C++17、异常/RTTI 和 TLS_NELEM=8；当前仅在编译中，无完成或上板结果。下表的 smp-load 输入快照不被这一新候选计划覆盖；具体依赖满足情况应由主任务后续真实探针更新。

| 依赖 | 固定源码位置 | 当前候选 / NuttX 处理建议 |
| --- | --- | --- |
| C++17 / STL / exceptions | src/CMakeLists.txt:35，ggml/CMakeLists.txt:222；src/llama-model-loader.cpp:77、155；src/llama-grammar.h:111 | llama 与 ggml 都要求 C++17；vector/string/unique_ptr/regex 与异常路径真实存在。不能仅打开 C 编译，也不能直接加 -fno-exceptions。先启用并验收完整 C++ runtime、静态构造/析构、异常传播与内存不足行为。 |
| 静态初始化与锁 | ggml/src/ggml-threading.cpp:4；ggml/src/ggml-backend-reg.cpp:310 附近 get_reg；ggml/src/ggml-cpu/ggml-cpu.cpp:36 | 全局 std::mutex、局部 static registry/vector 的线程安全初始化需要 C++ ABI guard 和互斥支持。核心注册初始化应串行，不能在运行中并发注册/卸载。静态注册表候选仍需要这些能力。 |
| TLS / errno / runtime | ggml/src/ggml.c:25、278；src/llama-mmap.cpp:180；ggml/src/ggml-cpu/amx/mmq.cpp:206 | 选中的通用 CPU 推理源未发现显式 thread_local；AMX 的显式 thread_local 不在本候选启用范围。不能因此推断所选 C++ 异常实现、errno、pthread runtime 不需要 TLS。当前 CONFIG_TLS_NELEM/TASK_NELEM/NCLEANUP=0；由实际 NuttX C++库配置、符号和多线程探针确定需求，禁止凭经验填固定槽数。 |
| pthread / 条件变量 / join | ggml/src/ggml-cpu/ggml-cpu.c:1336、1356、13661、13709；ggml/src/CMakeLists.txt:319 | OpenMP 关闭后 CPU pool 仍需要线程、mutex、cond、join。NuttX 应实现真实等待/唤醒和退出监督，不能返回成功空实现。Windows 分支使用 Win32 线程/同步，本轮不是 NuttX POSIX 线程兼容测试。 |
| pool 创建失败、OOM | ggml/src/ggml-cpu/ggml-cpu.c:13666、13687、13709；ggml/src/ggml.c:321 | pool 分配后直接解引用，创建线程失败 GGML_ASSERT；某些 malloc 包装会 GGML_ABORT。首个移植需预先限制线程/预算，并补部分创建失败的停止、join、释放与错误返回路径。只捕获 C++ exception 不能兜住所有 C abort/空指针。当前候选未修复或注入这些失败，不能作可靠性验收。 |
| 线程数 API 缺实现 | ggml/include/ggml-cpu.h:57 | b5046 声明 ggml_threadpool_get_n_threads，但源码搜索无定义且本轮真实链接失败。探针使用已实现的 pool_new、set_n_threads，不伪造 getter。记录传入 2/4 参数并计算校验，未测量板端线程分配或核利用率。 |
| 亲和性 / 调度优先级 | ggml/src/ggml-cpu/ggml-cpu.c:13117、13173 | __gnu_linux__ 分支以外的 unsupported 分支直接返回 true，不证明任何绑核成功。NuttX 必须增加真实平台路径并检查返回值/运行 CPU，或明确不支持并拒绝非默认请求。不能把用户设的 A72 [4,5] 当作已生效；本轮无绑核验收。 |
| C11 原子 / 内存屏障 | ggml/src/ggml-cpu/ggml-cpu.c:1375、2454 | pool graph/barrier 使用 atomic 和序列一致性屏障。必须由 ARM64 工具链和 NuttX SMP 环境验证，不能替换成 volatile。量化核可另有对齐要求。 |
| 单调时间 | ggml/src/ggml.c:498、504 | 非 Windows 路径 clock_gettime(CLOCK_MONOTONIC)。核对时钟精度、溢出、跨核一致性；主机成功不证明板端实现。 |
| 文件 open/read/seek/size | src/llama-mmap.cpp:163、175、189、203；src/llama-model-loader.cpp:478、546；ggml/src/ggml.c:541 | 模型加载器需要普通可读文件、确定长度与随机 seek，可能多分片。非 Windows 分支把 size_t offset 转 long；需证明 ARM64 ABI/long/off_t 足够和超范围拒绝，测试短读、截断、损坏、错误关闭。eMMC BCH 只读块路径不等于已能 fopen GGUF。 |
| mmap/munmap/madvise | src/llama-mmap.cpp:13、288、322、426、450；src/llama-model-loader.cpp:821 | 探针设置 model_params.use_mmap=false，但这只关闭运行路径，不自动删除已编译平台引用；b5046 没有本候选可直接使用的 LLAMA_MMAP=OFF CMake选项。NuttX 需核对 unistd 的 _POSIX_MAPPED_FILES 定义及 sys/mman 接口，或显式能力编译门控选择上游 unsupported 分支。不能用 mmap 返回伪地址。 |
| mlock/munlock/resource | src/llama-mmap.cpp:20、457、493、593；include/llama.h:318 | use_mlock=false 同样只是参数。_POSIX_MEMLOCK_RANGE 路径含 sys/resource，按平台能力裁剪；未支持时明确不可用。没有理由让 mlock 空实现返回成功。 |
| 对齐分配与释放 | ggml/src/ggml.c:242、278、1452；ggml/src/ggml-cpu/ggml-cpu.cpp:98 | ggml 对齐分配、普通 malloc/calloc、C++ new[]/vector 均存在。仅给 ggml_init 一个 arena 缓冲不足以接管模型权重、backend work_data、KV、元数据和线程栈。要分配域、对齐、上限、所有权与成对释放审计，禁止全局盲替换 malloc。 |
| 动态后端与 filesystem | ggml/src/ggml-backend-reg.cpp:6、111、140、233、482；ggml/src/CMakeLists.txt:216 | GGML_BACKEND_DL=OFF 仍编译 loader。candidate/ggml-backend-reg.cpp 删除扫描、dlopen/LoadLibrary 和 filesystem 路径，保留上游静态注册/查询；load 明确 NULL、卸载拒绝，不实现任何假 POSIX 函数。符号审计确认 ggml.a 不再有这类未定义导入。Windows EXE 仍依赖系统及 C++ runtime DLL，不宣称完全静态可执行文件。 |
| Linux NUMA / CPU 信息 | ggml/src/ggml-cpu/ggml-cpu.cpp:266；ggml/src/ggml-cpu/ggml-cpu.c:12748 | /proc/cpuinfo、Linux NUMA affinity 为平台条件分支。原生 NuttX 不应定义 __linux__ 去冒充兼容；不启用 NUMA策略，核信息从 BSP 真接口提供，不能造 /proc 内容。 |
| ARM 指令与混合核 | ggml/src/ggml-cpu/CMakeLists.txt；ggml/src/ggml-cpu/ggml-cpu.cpp:57 | 本轮为 x86-64 SSE4.2 主机，GGML_NATIVE=OFF 不等于通用所有 CPU。AArch64/NEON 与可选 dotprod/i8mm 应按真实 A53/A72 可用指令和线程亲和性编译验证，不套主机 flags；不得因 RK3576 型号默认启用扩展。 |
| 日志、环境、abort | ggml/src/ggml.c:68、130、173；src/llama-model-loader.cpp:451 | 部分系统的 backtrace 会 fork/exec 调试器；NuttX 条件分支应保持未支持，不能加 Linux 宏。getenv/日志属于可裁剪能力，错误必须返回或由受控故障处理报告。prompt/凭据不得进入模型日志。 |
| 量化 / 数学库 | src/llama-quant.cpp:51、422、512；ggml/src/CMakeLists.txt:321 | 当前静态库仍编译模型量化对象及多架构模型定义，未宣称达到最小字节数。可在后续按链接可达性进一步剔除离线量化工具 API；不可误删 Q4_K 解量化运行核。libm、STL regex/unicode 路径仍需支持。 |

当前固件输入证据（input/artifacts/smp-load-20260910/.config）：HAVE_CXX:1609 未启用；HAVE_CXXINITIALIZE:1610 未启用；USBHOST_MSC:816、FS_FAT:1240、FS_FATFS:1274 未启用；TLS:1529..1531 为 0，pthread 默认栈:529 为 8192。普通约126MiB堆与显式1GiB arena的分离、模型路径缺口来自固定输入方案文档，未重新测量硬件。

建议板端门禁依次为：C++ ABI/线程/时钟/对齐分配探针 → 失败创建与预算清理修复 → 静态 CPU 图探针并验证真实 CPU 归属 → 大文件只读随机读取 → 固定模型 SHA 的加载/短推理。没有权重的这次主机图计算不能替代后两项，也未验证 Qwen tokenizer、GBNF、KV cache 或 token 性能。

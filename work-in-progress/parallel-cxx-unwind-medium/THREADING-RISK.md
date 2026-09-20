# 多线程异常上线边界（2026-09-10 增量）

结论：当前基础异常探针可以继续验证，但不足以批准多个线程并发异常。GCC 的 `Thread model: single` 是 libgcc 同步策略需要核对的实质信号，并不表示 NuttX pthread 或独立构建的 LLVM libc++abi 不能使用线程。现有证据不能证明已经发生竞争，也不能证明所有异常展开共享状态都安全。

## 本轮证据分层

本代理只读新 ELF `artifacts/cxx-unwind-20260910/nuttx`：SHA256 `493d3246afabf1734f28cc1c1dbf3b5cfe786235fa4cfbc3f154c1bed5e71da2`，门禁通过，2 CIE、222 FDE，见 integrated-audit.json。符号表确实含 `unseen_objects`、`seen_objects` 两个全局生命周期的本地对象，以及 `__cxa_get_globals[_fast]`、pthread_once、pthread_getspecific、pthread_setspecific；符号共存不是调用关系证明。threading-evidence.json 保存本轮命令与哈希。

时序说明：原 HANDOFF.md、input-source-hashes.json、run-evidence.json 是主会话应用补丁之前的记录。随后主会话已应用两文件补丁并独立构建，新正式文件变化是预期集成。本次没有重跑原 collect_evidence.py 或正向apply检查，也没有覆盖这些旧证据；未来对已应用文件再次正向check失败不能归因于原CRLF或声称源码未变化。

以下为主会话已核对并回传的事实，本代理未访问SDK重查：精确 aarch64-none-elf GCC13.4.0 的 `-v` 含 `--disable-threads --disable-tls` 及 `Thread model: single`；注册函数实际 `bl __register_frame`；k7cxx_main FDE覆盖 `404556ac..40455cd4`；nx_start 在579/588行初始化堆，826行nx_bringup；nx_start_application 先执行lib_cxx_initialize再task_spawn。此补充关闭旧HANDOFF中相应待集成核对项，但不冒充本代理独立反汇编结果。基础探针运行状态以主会话真机证据为准。

## 两层不同的线程状态

LLVM libc++abi 管理每线程的已捕获异常栈与未捕获异常计数。17.0.6源代码有单全局、原生thread_local、TLS key三个分支；TLS key分支通过一次初始化和线程特定存储分离状态。启用pthread后，这条路径不需要编译器原生TLS，因此 GCC `--disable-tls` 不能单独否定它。当前配置TLS_NELEM/TLS_TASK_NELEM都是8也不单独证明所选分支正确。[固定版本实现](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-17.0.6/libcxxabi/src/cxa_exception_storage.cpp)

LLVM pthread适配中 once/key/get/set分别对应 pthread_once、pthread_key_create、pthread_getspecific、pthread_setspecific。应保留实际 libc++abi 预处理宏/编译参数，排除 `_LIBCXXABI_HAS_NO_THREADS`，并从 `__cxa_get_globals_fast` 追到真实NuttX pthread实现；不能仅检查全ELF里存在pthread符号。[固定版本适配](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-17.0.6/libcxx/include/__threading_support)

libgcc 管理共享FDE登记和查找结构，是另一层。相邻GCC13.2实现通过gthread锁保护对象列表，查找还可能延迟建立排序缓存；内存不足时后续查找可能重试初始化。当前ELF的seen/unseen符号与这类后端一致，但精确13.4预处理源码及机器码锁路径尚需核对。单线程工具链很可能把相关同步化为空操作；它不会因为另一个库链接了pthread而自动升级。[GCC13.2固定源码参考](https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-13.2.0/libgcc/unwind-dw2-fde.c)

当前探针先在主线程抛出并捕获，再创建工作线程；这可能提前初始化共享索引并掩盖首次并发路径。一次预热不是同步设计：还需排除分配失败重试、新登记表、其他展开入口及可变缓存。只限定单核亲和性也不能排除抢占竞争。

## 有界上线门禁

1. 保存精确工具链版本、实际选中libgcc.a路径/哈希、构建配置和unwind对象来源；只读反汇编 `_Unwind_Find_FDE`、登记/注销路径，辨认锁或原子操作及共享写入。不能用“不含pthread调用”当作无锁证据，因为也可能用原子/其他锁。审计相关一次初始化和其余共享状态，限定不在中断中展开。
2. 独立验证 libc++abi TLS：两个同时存活线程获得不同的 `__cxa_get_globals()` 指针（仅测试接口），嵌套抛出/重抛时各自计数正确，线程退出后TLS析构释放，反复创建不会耗尽key或稳定泄漏。还要验证不同NuttX task group的情况，不能只测同一std::thread组。必须保留测试前后堆/TLS状态；不通过读取私有结构硬编码布局验证。
3. 同步屏障放行两个工作线程，在不同CPU上各自内部throw/catch，使用跨noinline函数调用链的RAII精确计数；每次异常留在线程内部。应分别覆盖冷启动首次并发与主线程预热后的并发，多轮重抛/exception_ptr（若产品会用）、线程结束回收。有界迭代、截止时间和主会话认可的恢复路径；未设计安全回收前不得超时销毁仍运行线程的共享状态。
4. 内存受限故障注入只在独立诊断版本中进行，避免损害无线系统。覆盖异常存储分配和FDE缓存初始化失败后重试。完成静态同步证明再做压力回归；压力跑过不等于无数据竞争证明。每个结果绑定实际镜像哈希。

## 最小修正方向（本次不修改补丁）

短期可以把产品范围限定为单一异常使用任务：其余工作线程和调用的库必须审计为不会抛出或使用展开API，并把错误转换为返回码。仅给显式throw加锁不够，new、容器、库函数都可能隐式抛出；不应把这项约束包装成通用多线程支持。

真正需要并发异常时，优先锁定13.4源码，为所用libgcc unwind后端接入NuttX有效的gthread互斥/once支持，或者独立重建该后端的受控替代对象；保持ABI和编译选项一致，确保链接只选中一套实现，再检查实际机器码。互斥实现必须在构造前可用，不能自身抛异常或递归触发展开；分配、锁次序和可重入性须另验。通常只保护共享FDE状态临界区，不应持全局锁跨越整个用户析构/异常处理流程，否则可能与用户锁死锁。

不推荐直接在 `_Unwind_RaiseException` 外围加锁，也不建议把 `--wrap=_Unwind_Find_FDE` 当即用补丁：必须先证明所有内部/外部引用确实可被重定向，且覆盖登记、注销及其他共享写入；同目标文件内部引用可能绕过链接包装。切换LLVM libunwind也是可选工程方向，但需完整替换与重新验证，不是本轮最小补丁。

本次只增加风险说明和静态证据，不改变candidate.patch，不进行SDK、硬件、构建、中央日志或其他目录操作。

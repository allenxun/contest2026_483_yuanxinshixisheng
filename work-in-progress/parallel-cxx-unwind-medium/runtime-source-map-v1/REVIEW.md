# C++ unwinder 移植依赖审查

结论：最小合理构建单元至少同时覆盖 `unwind-dw2.c` 与 `unwind-dw2-fde.c`，使真实 NuttX once 和 mutex 生效；只重建 FDE 查找或只定义 `__GTHREADS` 均不够。现有 6 个文件是官方 releases/gcc-13.4.0 参考材料，不是 SDK 精确源码或完整构建输入。此次没有构建、替换、下载或执行设备操作。

## 源码与机器码对应

| 参考源码位置 | 条件/作用 | 冻结实际机器码与边界 |
|---|---|---|
| unwind-dw2.c:1338–1348 | `#if __GTHREADS` 使用静态 `__gthread_once_t` / `__GTHREAD_ONCE_INIT`；once 失败且 table[0]==0 时退回初始化。else 直接按 table[0] 判初始化 | uw_init_context_1 404dae08 查 table[0]，404dae70 先写 table[0]，404daeec 才写 table[31]，无 once 调用；与单线程分支一致 |
| unwind-dw2-fde.c:81–106 | 优先静态 `__GTHREAD_MUTEX_INIT`；否则 INIT_FUNCTION 加 once；都无则依赖后端无锁 stub | 当前列表实现没有保护搬移的有效锁 |
| unwind-dw2-fde.c:1224–1259 | mutex 覆盖 seen 查找、unseen 摘除、search_object、插回 seen | 实际 40450374 摘除、40450378 search_object、404503ac 插回；符合无锁列表交错窗口 |
| gthr-single.h:31–38,211–269 | 定义 int 类型、零 initializer，但不启用 __GTHREADS；once/lock/unlock 都为无效 stub | 因此看到 mutex initializer 宏不代表有锁；强行给此后端加 __GTHREADS=1 还会调用不运行 callback 的 once stub |
| gthr-posix.h:32–70,697以后 | __GTHREADS=1，pthread 类型和 initializer；once/lock/unlock 经 active 判断进入 pthread | 应用到新的目标对象后，必须用预处理与反汇编证明选择真实路径 |

这建立结构性对应，不证明 SDK 与上游源码逐字相同，也不从一次 cold abort 确定是哪一处窗口触发。实际 abort 在 uw_init_context_1 404dafbc；返回地址等于相邻 Phase2 入口不是 Phase2 出错的证据。现有 single/warm1 有限控制通过不构成后端线程安全证明。

一个容易漏掉的条件：fde.c:39–43 的 `ATOMIC_FDE_FAST_PATH` 自动定义位于外层 `#ifndef _Unwind_Find_FDE` 的 **else**。不能只看到 CAS4 宏就判断普通独立编译会走 btree；包含它的外部包装 TU 和最终预处理结果决定路径。最小候选保持普通注册列表实现，避免未经审查切到 dl/loader 或 btree 分支。若选择后者，6 文件还缺 unwind-dw2-btree.h 及其依赖，必须重新审查原子与析构生命周期。

## gthread 到 NuttX 的映射与缺项

| 需求 | 本地证据 | 尚缺的证明 |
|---|---|---|
| pthread_once_t / PTHREAD_ONCE_INIT | 精确 abi-macros.txt:2869 为 `{false, PTHREAD_MUTEX_INITIALIZER}`；ELF 有 pthread_once 404cc128 | 精确 pthread.h 类型布局，以及 pthread_once 源码/反汇编：并发等待、可见性、返回码、初始化早期可调用性 |
| pthread_mutex_t / PTHREAD_MUTEX_INITIALIZER | 宏:2139 使用 NuttX nxrmutex 初始化；ELF lock 404cbeb0、unlock 404cc020、init 404cbe14 | 当前 CONFIG_PTHREAD_MUTEX_DEFAULT_UNSAFE=1 的实际语义及错误/owner/cancellation 行为；不能由名称推断不是 SMP 锁，也不能忽略其约束 |
| pthread mutex/cond 扩展 | 当前 ELF 有 trylock/timedlock/destroy、cond init/destroy/wait/timedwait/signal/broadcast | 全 gthr-posix.h 的内联函数仍需匹配声明；mutexattr_init/settype/destroy、key_delete 等未在已链接符号清单检出，不等于 SDK 没实现，可能未引用被裁剪。需精确头/库清单 |
| pthread TLS | ABI 实际调用 once/getspecific/setspecific，ELF 有 key_create；宏 TLS_NELEM/TLS_TASK_NELEM 均8 | TLS 键耗尽/析构/任务退出及分组语义。unwinder 这两个同步点不需新的语言 TLS；保留 libc++abi pthread TLS，不能因工具链 --disable-tls 改成全局异常状态 |
| active 检测 | gthr-posix.h:85 按 SUPPORTS_WEAK && GTHREAD_USE_WEAK；非 glibc/bionic 常用 pthread_cancel 作为弱代理。当前 ELF 有 cancel | 静态归档弱引用不保证抽取实现。建议该候选明确 GTHREAD_USE_WEAK=0（最终预处理确认），让普通 NuttX 路径 active=1、pthread 强引用；不可定义 __GLIBC__ 绕过选择。如保留弱引用需另证明代理与全部依赖始终抽入且无 stub |

最小 unwinder 同步调用集是 once、mutex lock/unlock（若选动态初始化再有 mutex_init）；完整通用 gthr-posix 头会声明更多包装函数。不能通过只补几个伪 typedef 编过就称 ABI 匹配。全头兼容性测试应使用 NuttX 真实 sysroot，不使用裸机 newlib 的 pthread 头，也不使用主机 pthread。

## 可实施构建兼容性清单

1. 冻结实际 GCC13.4 构建来源/补丁、target 配置、multilib、libgcc 归档及现有链接 map。取得对应 GCC 构建规则（libgcc/Makefile 和 target fragments）的展开命令；本地参考包缺这些内容，暂不能给可复制的最终编译命令。
2. 生成头必须来自匹配目标配置：tconfig.h、tm.h、libgcc_tm.h、gthr.h 的实际选择/重定向（常见 gthr-default.h，需核对实际规则）。其转引的 auto 配置头以完整依赖文件为准，不能从宿主 GCC 复制。静态源码头还缺 tsystem.h/coretypes.h/dwarf2.h/unwind.h/unwind-pe.h/unwind-dw2.h/unwind-dw2-execute_cfa.h；目标条件可能还需 md-unwind-support.h。这些名字来自现有 include，不声称每个均为独立生成文件。保留 include 路径优先级和 -M 依赖清单。
3. 隔离目标构建中至少重新编译 unwind-dw2.c（包含 unwind.inc）和普通 unwind-dw2-fde.c，真实 pthread gthread，保留目标 AArch64 ABI、端序/LP64、寄存器展开规则、unwind context 扩展、隐藏可见性/符号版本条件、编译器优化与 unwinder 自身的展开信息。原工具链 arithmetic/builtin helper 可保留；不要把整个 libgcc 替换成另一平台归档。是否还需 unwind-c.c 等 personality 对象由符号归属/引用决定，不能凭这6文件列出完整运行库。
4. 对两个对象保存完整编译命令、-dM 和预处理文件，确认 __GTHREADS=1、真实 initializer、GTHREAD_USE_WEAK=0、未选 gthr-single，检查 _Unwind_Find_FDE 宏与 ATOMIC_FDE_FAST_PATH、目标 md 分支。检查未引入意外 TLS relocation、dl_iterate_phdr/Linux loader 依赖、libatomic 或缺失 AArch64 outline-atomic helper。选定原子 ISA 必须匹配实际核，不以编译成功代替运行要求。
5. 显式候选对象先于原 libgcc 参与解析，并检查完整最终 map/nm：所有 `_Unwind_*`、`__register_frame*`、`__deregister_frame*` 和其 object/list/once 状态只有一致实现。若归档仍抽入旧 FDE 或旧 dw2 对象，处理其符号依赖/归档选择，禁止 allow-multiple-definition。不能仅包装 `_Unwind_RaiseException` 或用大锁跨越 phase2/landingpad 来替代这些内部同步。
6. NuttX 初始化边界：现有注册在堆初始化后、可能抛出的 C++ 构造之前。新注册将调用 mutex，应另外证明该启动点 pthread mutex 所依赖的调度/TCB/同步设施已可用；即使静态 initializer 免分配也不等于可在任意早期调用。只在线程上下文展开，不扩展到 IRQ。注册表与其对象保持镜像生命周期，不能解锁后释放仍会被读取的 FDE；保留原 .eh_frame 终止/只读映射审计。
7. 链接后验证机器码实际 once 和 lock/unlock，以及 NuttX实现的同步效果，而非仅符号存在；随后由主会话在独立冷启动开展同链 single、首次双worker和反复多线程异常/TLS清理/资源回收门禁。主机可验证协议逻辑，不能证明目标 single-thread 工具链已被正确修复。FindFDE 预热与完整 throw 预热均不是这一构建路线的线程安全替代。

## 最小待提供输入

精确目标生成头/依赖清单、GCC构建规则/参数与归档成员；NuttX pthread.h、pthread_once 和 mutex 底层实现；两对象实际编译预处理及链接归属。现有材料只能确认 API/宏部分存在，尚不能确认完整头兼容、早期锁可用及重建 ABI 一致。因此本交付是移植依赖清单，没有产生可上板运行库。

所有引用都来自本地冻结材料；参考文件 URL 和 SHA256 由 sources.json 提供，audit.json 验证下载文件与该清单一致。没有进行网络访问或把上游参考描述成 SDK 精确构建源码。

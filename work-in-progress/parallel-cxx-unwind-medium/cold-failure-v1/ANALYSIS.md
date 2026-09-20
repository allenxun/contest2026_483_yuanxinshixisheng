# cxx-eh 首次双worker异常失败：有限定位

**已观察到展开器初始化附近abort，尚未建立现场根因。** 初始直接符号化把返回PC误指到相邻Phase2函数；实际反汇编要求纠正该定位。存在具体可审查的无同步FDE列表搬移窗口，但不应把一次失败定性为已证实竞态，也不能从两线程随后不在ps推断正常清理。主会话先恢复无线基线；本文不授权或实施额外硬件操作。

## 已证实与无法推断

本地ELF SHA256为 `aeed298960d61435e381a4f4323dbf5b08e1b1503fc97161ae821d0dfc29d19c`。正式探针与原候选集成记录对应，冻结输入哈希见evidence.json。runtime.bin仅有cold起始、CPU5 task13回溯和NSH提示符，没有worker计数、PASS/FAIL汇总、joined或REBOOT_REQUIRED。runtime.json报告0.047秒及workers=[]；first_call_intervals_overlap=false此时表示没有可比较区间，**不证明两线程未重叠**。

post-failure-ps仅保留idle、工作队列和NSH，没有探针线程/任务。可能是abort导致任务组退出等系统行为，需精确NuttX abort/exit路径核对；未见正常pthread_join，不能宣称探针计数、TLS析构、栈资源或其他应用状态完整恢复。探针自有stop/保持态只处理合作失败，不可能拦截运行库直接abort。

主会话最初直接符号化链为sched_dumpstack→abort→_Unwind_RaiseException_Phase2(unwind.inc:41)→_Unwind_RaiseException(unwind.inc:94)→__cxa_throw→leaf/middle/outer/one_throw/worker。收到精确反汇编后发现：记录的404dafc0恰好是Phase2入口，而Phase2自己的abort调用是404db0c4（返回PC应404db0c8）；相邻回溯帧404db4e4对应404db4e0的 `bl uw_init_context_1`，真正Phase2调用却在404db5c8（返回PC404db5cc）。随后取得的uw_init_context_1.txt证实其末条404dafbc就是 `bl abort`，返回地址恰好404dafc0。**本轮栈链定位应修正为uw_init_context_1内abort，而不是已经进入Phase2。** 不能因相邻函数入口行号误导就修改landingpad。

该函数有两个条件汇入同一个abort：404dadfc在uw_frame_state_for返回非0时跳转；404dae18在共享字节表第31项不等于8时跳转。现场没有保存分支或相关寄存器，当前不能区分触发了哪一条。前者不是仅凭回溯即可证明“FDE不存在”，还需实际返回码/查找结果；后者也不等于现场已经证明初始化竞争。

本代理实际readelf检查到以下FDE和LSDA augmentation，原始输出frames.txt：

| 函数 | FDE范围 |
|---|---|
| leaf | 40455cd4–40455d18 |
| middle | 40455e9c–40455ec0 |
| outer | 40455ec0–40455ee4 |
| one_throw | 40455ee4–40455f8c |
| worker | 40455f8c–404560b0 |

因此不是“这些函数整段缺FDE”的简单情形。既有静态审计263FDE通过也不验证运行时查找、CFA恢复、LSDA动作或落点正确。三个noinline层各有Guard，one_throw内部捕获payload和catch-all；源码没有让正常payload逃出noexcept边界的意图。优化可能改变落点组织，但仅看到优化开启不能称编译器有错。

## 三条待区分假设

1. **共享展开状态的首次查找/排序。** 精确工具链single线程配置，ELF含seen_objects/unseen_objects。实际_Unwind_Find_FDE反汇编显示40450360加载unseen首对象，40450374先把unseen改为next，40450378执行search_object，随后404503ac或40450404才插入seen；没有保护这段搬移的锁调用、原子序列或临界区指令。对仅有一个已注册对象的情形，第一核取走unseen到挂入seen之间，第二核可以看见两个列表都空并返回NULL。这是从机器码构造的具体可行交错，提升了优先级；但尚未记录现场第二核所见列表或确认触发时仅一个对象、是否已预热，不能冒充该轮原因已经证实。

   **还存在独立的共享寄存器尺寸表初始化窗口。** uw_init_context_1先在404dae08读取表[0]决定是否跳过初始化；404dae70把表[0]写8，直到404daeec才把表[31]写8，而后者恰是404dae14–404dae18的断言条件。另一核可能在两次写之间看到“已初始化”哨兵却看到尚未写好的第31项并abort。机器码没有相应发布/once同步。这使“只预热_Find_FDE”不够覆盖全部已发现冷路径；成功的完整单线程throw/catch会经过尺寸表初始化，故实验B更有区分力。仍不能从一次统一abort落点分辨现场是列表窗口还是尺寸表窗口。
2. **异常运行库线程状态初始化/隔离。** 已收到精确宏与反汇编：_LIBCPP_HAS_THREAD_API_PTHREAD存在，_LIBCXXABI_HAS_NO_THREADS和HAS_THREAD_LOCAL均未定义；__cxa_get_globals_fast在404c2dd4调用pthread_once、404c2df4尾调pthread_getspecific；__cxa_get_globals按需分配16字节并在404c2e38调用pthread_setspecific。因此排除“此libc++abi编译成单个全局eh_globals”这个具体猜测；实际pthread隔离/实现错误仍需另证。两线程共享key正常，共享返回对象才可疑。主线程预热不消除每个新worker首次TLS分配，所以warm双worker仍有区分意义。
3. **与并发无关的多层清理/ABI/优化落点。** 基础k7cxx是在主线程以另一调用链通过，并不证明本探针三层函数在CPU5的清理可用。单worker同路径首次异常若也失败，应优先排查精确FDE、CFA、LSDA和personality处理、线程栈/ABI差异。只降低优化而改变结果，仍不足以单独证明优化器bug。

## 最小区分实验（由主会话另行实施）

每项独立新RAM启动、固定相同工具链和三层throw代码，记录实际镜像哈希；一次异常足够第一轮定位，先不增加压力。外部截止与基线恢复先准备好；失败后不在同一镜像重复运行。

| 实验 | 改动/约束 | 区分力 |
|---|---|---|
| A：单worker cold CPU5 | 只创建1线程；真实ready/permit门也按1参与者；仍不主线程prethrow；保留三层RAII及join | 若失败，则不需要两个探针worker并发就能触发；转查单线程多层展开/worker TLS/CPU或栈。不能仅让线程1不throw却留下双人barrier |
| B：主线程同路径预热→双worker CPU4/5 | 首先单次one_throw检查通过并输出PREHEAT_PASS；然后双worker各1轮 | 预热本身失败首先定位主线程同路径；预热通过但worker失败提示线程/并发路径；B通过且A通过、原cold失败支持首次共享初始化方向但不证明竞态 |
| C（仅A/B无法区分时）：双worker存活、严格串行首次throw | 同时创建两线程，先只放行一个，完成后再放行另一；不主线程预热 | 保留两个线程的TLS存在条件，排除两个throw重叠；通过仍只说明受控串行路径通过 |

已有warm命令预热后为64轮，而且没有PREHEAT_PASS标志；可先只读评审其逻辑，但为解释失败位置和控制变量，定位版宜明确1轮/独立preheat标志，不直接把64轮结果与cold1轮做唯一因果对照。CPU4单worker可作为A的后续核对，不把固定CPU0当修复。第一次测试不增加__cxa_get_globals调用，因为那会主动预初始化TLS而改变cold条件；TLS地址探针应作为单独明确预初始化的后续实验。

## 已向主会话请求的精确资料

- 实际GCC13.4 libgcc/unwind.inc至少1–110行，最好同版unwind-dw2-fde.c、gthread选择；_Unwind_RaiseException_Phase2、_Unwind_RaiseException、_Unwind_Find_FDE反汇编。
- 实际__cxa_get_globals[_fast]反汇编；cxa_exception_storage.cpp所选预处理分支与pthread TLS实现。先看代码路径，不在cold里加会改变状态的打印/调用。
- 探针40455cd4–404560b0反汇编、对应.gcc_except_table及CIE编码，核对逐层cleanup landing pad和__Unwind_Resume路径；最好保留带行号符号化时对回溯return-PC与PC-4的区别。
- 若需要解释任务消失，精确NuttX abort/exit/task-group终止路径；不推导未记录的pthread_join。

## 最小措施方向与边界

优先实施上述A/B区分实验，不改锁、不替换libgcc。若需要进一步明确现场分支，可在**另一个诊断构建**对两个abort前置点分别记录返回码/尺寸字节及原因编号，或通过受控调试器取得寄存器；这是主会话需另评审的侵入式变化，会改变时序，不是本次已做或建议立刻上线的补丁。

boot/业务启动时序上的有限缓解可以评审为：在heap、libc++abi TLS和异常登记可用之后、任何其他线程可能使用展开器之前，串行执行一次完整自捕获throw/多层RAII探针，成功后经有效同步才允许工作线程进入。仅调用_Find_FDE只能触及登记/排序，不能初始化上面尺寸表，因此不能声称解决本次两个候选窗口。

即便完整预热通过，该措施也只适用于**不变单镜像、没有之后注册/注销、所有相关共享初始化已完成并可靠发布、后续不会重试延迟分配**等明确受限条件。成功throw并不公开证明FDE排序缓存分配成功；如果search_object内分配失败退回线性查找、之后再次尝试初始化，仍可能有共享写入。需要精确search_object/init_object代码/机器码及状态证据才能建立这些前提。它不是通用并发锁方案，也不能把warm通过写成single-thread libgcc线程安全。长期需要真正的同步/受支持多线程unwind后端仍沿用THREADING-RISK的评审方向，本次不重写它。

主会话已采集evidence/cxx-eh-20260910/diagnostics的函数/探针反汇编、LSDA、libc++abi源码和宏，index.json保留其采集命令，diagnostics-inputs.json冻结本地输入哈希。GCC源码搜索结果为空，调试路径不表示源码实际存在。本代理Web对固定unwind.inc读取失败，未用其他版本行号替代。没有自行SSH、读取SDK或修改锁。证据、工具和分析仅写本目录，旧交付不变。

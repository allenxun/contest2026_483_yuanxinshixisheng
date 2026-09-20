# k7eh 两线程异常探针候选

本目录为全新交付，不改动上一批冻结交付或正式源码。主会话已报告 cxx-unwind 基础主线程异常真机通过；本候选尚未ARM64编译、未上板。目标工具链是GCC13.4.0单线程配置，主机运行不能证明其共享展开状态安全。

## 接入和执行

`k7eh_main.cxx` 是单个新增应用源，入口为 `extern "C" int k7eh_main(int,char **)`，建议主会话独立注册 `k7eh` 应用，与旧 `k7cxx` 分开。在现有C++异常/RTTI/pthread/SMP8配置、已修复的异常表注册基础上，示意CMake为：

```cmake
nuttx_add_application(NAME k7eh SRCS k7eh_main.cxx STACKSIZE 16384 PRIORITY 100)
```

这是接入说明，不自动复制或改应用清单。目标编译不得定义 K7EH_HOST_TEST 或任何故障注入宏。必须确认 `__NuttX__` 分支启用且至少有CPU4、CPU5；此候选通过正式k7smp相同的pthread属性API绑定这两个核，不回退到CPU0。两个工作线程各16KiB栈，主线程16KiB示意配置；另有小型静态状态、pthread控制块、异常对象及运行库内部开销，不能将总内存声称为精确48KiB。没有容器、动态字符串或模型内存。

- 新RAM启动后先执行 `k7eh cold`：2线程、各1次throw。调用此命令前不能执行k7cxx、其他抛异常应用或回溯/展开工具；所有后台线程及构造也必须核对没有提前触发FDE查找。探针只能保证自己的协调线程没有预先throw，不能自动证明整个系统是冷状态。
- 再次新RAM启动后执行 `k7eh warm`：协调线程明确先完成1次同路径throw/catch，然后2线程各64轮。每轮双方就绪后由同一原子permit放行，下一轮就绪意味着上一轮已完成，防止一条线程跑完而另一条尚未开始。
- 全局attempted只允许本应用每启动一次尝试；旧k7cxx的once标志不共享，因此必须由主会话控制启动顺序。不能同一启动先跑cold再warm。

pthread C创建接口避免std::thread构造失败在协调线程抛异常而污染cold。payload为两个unsigned，经过3层noinline函数，每层RAII计数一次；捕获类型和worker/round字段必须匹配。cold期望每线程caught=1/cleaned=3，warm期望caught=64/cleaned=192，所有errors、cpu_mismatch为0。结果记录首次调用的单调时钟区间，可观察是否重叠，但区间重叠或同时放行不等于证明发生了libgcc共享状态竞争。结果故意保留 `concurrency_proven=0`；PASS只表示本轮功能断言通过。

## 生命周期与截止边界

最多创建2个joinable线程；工作状态、参数、句柄均为静态对象。创建第0个失败时无线程需收回；第1个失败时设置stop，使已创建线程从等待门退出，再join。只有所有已创建线程join成功才返回并输出joined数量。attr_destroy错误不能把成功创建的线程误判成未创建而丢失所有权。

正常阶段就绪放行共享最多5秒预算，完成等待最多5秒，失败后合作退出宽限最多2秒。工作线程遇到停止不会继续下一轮，所有普通失败路径都回收线程。不能安全强制取消可能卡在异常展开中的线程，done标志也早于pthread退出/TLS析构，因此真正回收需要join。

若宽限后仍未退出或join返回错误，协调任务输出 `REBOOT_REQUIRED owner_retained=1` 后仅休眠保持，不退出任务组、不销毁状态、不假称释放了资源。pthread_join本身仍可能在损坏运行库/TLS析构中阻塞，无法仅靠本进程获得硬截止。主会话必须在加载前准备独立外部截止和恢复方案，例如15秒无最终结果即采集有限状态后按既有授权恢复；若join卡住可能连REBOOT_REQUIRED也不会输出。这个保持态是失败资源保全，不是有界执行成功。不要在失败镜像重复启动探针。探针没有写存储、启用外设、强制重启或取消其他任务。

## 主机原始结果

运行 `python -B run_host.py` 可在此目录复现。host-results.json含全部14条实际命令及输出：编译器信息、5个严格 `-Wall -Wextra -Werror` 构建、8次运行情形。全部退出码符合预期：cold/warm成功、repeat拒绝、参数拒绝、线程0创建失败、线程1创建失败且线程0回收、延迟就绪导致合作超时且2线程回收、RAII计数故障拒绝。慢就绪仅主机宏下把阶段预算改为20ms并延迟100ms，2秒宽限确保可验证合作退出；未注入真实永久卡死。宿主每条命令20秒超时只是测试进程看护，不是目标线程安全取消机制。

宿主为Windows x86_64 MinGW GCC12.2.0，Thread model: posix，异常后端为SEH。目标为ARM64 GCC13.4.0、单线程libgcc/DWARF展开，且libc++abi使用独立pthread TLS。宿主验证只覆盖探针协调、计数和清理逻辑，不覆盖目标FDE首次排序、GCC gthread锁、TLS隔离、SMP内存竞争或真实板端栈空间。未重新执行上一批不变工具测试。

## 主会话未完成门禁

1. 核对输入哈希、目标条件和API可编译性；独立构建，不覆盖已完成产物。确认noinline三层有独立FDE、清理区和LSDA；原ELF审计工具只提供静态部分证据。
2. 核对精确libgcc13.4共享列表/缓存与锁实现，cold开始前是否已被后台使用。不将本次探针替代先前THREADING-RISK的同步审查。
3. 先规划恢复，再由主会话新启动执行cold，另一次新启动执行warm；保存完整输出、实际镜像哈希、CPU绑定、堆和栈峰值。若首次区间不重叠，说明本次没有观察到调用区间并行，不能仅靠PASS宣称并发压力覆盖。
4. 单次cold仅2次异常，统计发现能力有限。若静态审查允许，再在不同新启动重测cold；不要自行扩大此候选迭代/核数。此版本未覆盖嵌套重抛、exception_ptr、跨task-group TLS、OOM缓存重试、长稳或无线共存验收。

所有输入哈希在host-results.json；delivery.json索引本目录全部交付，包括原始结果与主机构建产物。没有接触SDK、VM或硬件。

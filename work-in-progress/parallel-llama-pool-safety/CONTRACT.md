# 固定 ggml POSIX 线程池安全候选

来源为 llama.cpp commit `74d4f5b041ad837153b0e90fc864b8290e01d8d5`。新目录从前一交付的官方源码归档复制并核对 SHA，没有重新下载或修改旧交付。改的是实际 ggml-cpu.c 的池生命周期和隐式池错误检查，不是独立模拟池。正常运算仍由该版本真实 ggml CPU 核执行。

## API 与所有权

`include/ggml-pool-safe.h` 暴露 `ggml_pool_create_checked` 与 `ggml_pool_destroy_checked`，返回 errno 值。创建先验证参数、亲和性支持、线程数和预算，任何不满足都不启动工作。分配、mutex/cond/attr 初始化及逐个 pthread_create 均检查失败；记录实际成功创建的数量，失败时只停止、join 那些已经创建的线程。未初始化资源不销毁。

每个池由单一 owner 创建、运行图和销毁；不能在图尚未完成时销毁，也不能让两个 owner 同时操作同一个池。不同池各有自己的 hooks 和记录，不使用全局故障注入开关。hooks.ctx 必须活到成功销毁，note 可在多个真实 worker 上调用，须线程安全、非阻塞、不可重入销毁。fail 只由创建/销毁 owner 调用。

通常创建失败后 `*out=NULL` 且已释放资源。如果停止/唤醒/join/销毁没有成功，返回错误并保留 `*out`，它是待清理池，禁止计算。调用方保存指针并重试 destroy_checked，不能按普通“创建失败”丢弃指针。重试跳过已成功 join 和已销毁对象；只在全部确认退出后释放 worker数组和池本身。

故障注入在真实操作之前返回失败，从不提供假分配指针、假线程句柄或假 join 成功。每个成功的线程都由真实 pthread_create 启动原 ggml worker，并由真实 pthread_join 回收。加入的 note 只观察真实获取/释放和 worker进入/退出/计算，不替代操作。

## 资源预算

默认最多4线程（含调用者）、每个辅助线程请求256KiB栈、预算4MiB。`ggml_pool_required_bytes` 检查乘加溢出；按池结构 + n个worker结构 + (n-1)×请求栈字节核算，在任何池分配前拒绝超限。pthread_attr_setstacksize 的实际失败也走清理；属性对象随池保留，销毁时检查其返回值。

这是单池的准入额度，不是实际全进程峰值或物理内存预留。pthread实现的栈取整、TLS、调度对象、libc分配元数据、调用者栈、图buffer、weights/KV/backend scratch等不包含在此预算。多个池的累计额度也须由上层统一准入。没有把 1GiB arena 接管为 malloc，没有量化或测量模型内存。

计数测试验证本候选管理的池字节、mutex、cond、attr、未join句柄和仍运行worker均归零；不等同于整个 ggml/C++ runtime 的全量堆泄漏检查。

## 亲和性与平台

本候选 `ggml_pool_affinity_supported()` 明确返回 false。任何非空cpumask、strict_cpu或非默认优先级请求，在分配前 ENOTSUP；不会因上游unsupported分支返回true便假报绑核。NuttX后续必须新增真实能力检查、逐worker设置结果与运行CPU证据，完成后才允许这些参数。当前只是默认调度下的主机计算，不是A72绑定验证。

根 CMake 用 GGML_POOL_POSIX 显式绕过 ggml-cpu.c 的 Windows线程模拟和 Windows池同步宏，走真实 MinGW POSIX pthread_create/join/mutex/cond 路径；未伪定义 __linux__，其余Windows CPU/时钟代码保持正常平台。nm证据确认CPU库导入pthread操作而非CreateThread模拟。此候选不支持OpenMP路径，编译期拒绝，不能无条件应用于其他ggml配置。

## 上游 API 限制

兼容的 `ggml_threadpool_new` 默认使用上述4线程/4MiB策略：已成功清理的分配/初始化/创建失败返回 NULL，并设置 errno。隐式图池创建失败返回 GGML_STATUS_ALLOC_FAILED，避免接着解引用NULL。调用方仍须检查显式池返回值；不能把 NULL 传到别的未检查API后声称安全。

原指针返回和void free接口无法转交“清理失败仍持有资源”的状态，所以在这种异常清理失败中仍有GGML_ABORT；需要可恢复语义的集成必须使用checked API并保留指针。当前移除的是普通分配/线程创建失败的断言终止，未承诺所有库故障都无abort。join等待本身没有库内截止时间；若运行中的图/系统线程不退出，owner可能等待，测试由独立子进程30秒限时兜底。后续NuttX应在owner层安排有界监督与保留资源，不能超时后强行free。

未改造图allocator、模型加载器、std::vector/new失败、C++异常和整个ggml的GGML_ASSERT。原算子和worker运行期的mutex/cond错误处理也不是本次完整重写范围。upstream的其他扩展API（包括未实现的pool线程数getter）保持原状。

NuttX主会话通知：libc++ thread.cpp还需要TLS_TASK_NELEM>0，首次失败已保留，正在cxx-tls-20260910尝试TLS_NELEM=8/TLS_TASK_NELEM=8。此为主会话消息中的编译中状态，本候选未访问SDK或验证该配置。

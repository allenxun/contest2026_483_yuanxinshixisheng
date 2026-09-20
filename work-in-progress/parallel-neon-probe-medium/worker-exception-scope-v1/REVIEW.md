# 当前2/4线程小图的异常范围审查

结论：在固定源码、当前构图成功、默认扩展宏/日志配置和回调不变的前提下，**当前worker正常计算路径未发现C++ throw、new或动态容器分配；它确实调用C++函数，不能说“worker只执行C”**。这只是64×64 F32逐元素乘法的路径结论，不证明整个llama推理线程可抛API均在owner，也不证明single-thread libgcc具有线程安全异常支持。没有运行目标或并发异常测试。

## 精确的小图范围

`graph_probe.c:gp_run`只接受2或4线程：owner先ggml_cpu_init，创建checked pool，再用静态arena建立两个64×64 F32张量与ggml_mul结果，建图、ggml_graph_plan、最后ggml_graph_compute。此处是**逐元素乘法GGML_OP_MUL**，不是矩阵乘法MUL_MAT、量化或模型计算。工作区在gp_state中预留，plan不足即拒绝；没有走CPU backend的new[] work_data路径。plan由memset初始化，abort_callback未设置。

物理CPU没有采样/绑定，本probe输出已明确default_unbound、physical_cpu_observed=0；2/4指逻辑参与线程数，不能独立证明多物理核并行，更不能推导并发异常安全。

## 正常worker调用链

1. `candidate/ggml-cpu.c:13724`真实pthread_create启动`ggml_graph_compute_secondary_thread`（13596）。入口/计算/退出的pool_note调用本应用`graph_probe.c:note`，只操作C11原子；没有分配、日志或外部动态回调。checked创建/分配/fail hook和join销毁由owner执行，worker没有自己的try/catch恢复层。
2. worker等候条件变量/stop/pause，进入`ggml_graph_compute_thread`（13483），最终用原ggml_barrier同步。此次无NUMA请求、cpumask、优先级变更；NuttX没有__gnu_linux__路径，相关平台分支须以实际预处理确认，不可把未知平台分支当真实affinity验收。
3. `ggml_compute_forward`（12349）先调用`ggml_cpu_extra_compute_forward`。**这是C++边界**，在ggml-cpu-traits.cpp迭代`ggml_backend_cpu_get_extra_buffers_type`返回的静态std::vector。
4. 该vector的首次初始化（ggml-cpu.cpp:36）包含push_back(NULL)，即使无额外backend也会潜在分配/抛bad_alloc。但本图owner在计算前`ggml_graph_plan`（candidate:13324）逐节点调用`ggml_cpu_extra_work_size`，访问同一个vector；成功plan返回意味着它已完成初始化，worker正常只读取。初始化失败则不能宣称graph已成功进入计算，当前C入口没有把这类C++异常统一转errno。pthread已经存在并不意味着它们同时展开异常。
5. 当前CMake没有添加GGML_USE_CPU_AARCH64/KLEIDIAI/AMX/ACCELERATE/OpenMP宏；在这些扩展未由全局配置另行注入时，extra列表只有NULL。即便审到AArch64 extra类型，其get_tensor_traits（aarch64.cpp:5699）只匹配MUL_MAT/MUL_MAT_ID，因此本MUL返回nullptr。但其他可选扩展未知，必须以实际编译宏为准。
6. switch进入`ggml_compute_forward_mul`→`binary_op<op_mul>`→`apply_binary_op<float,float,float>`→`vec_binary_op_contiguous`。binary-ops.cpp中只做行分片/指针偏移/标量浮点乘；common.h的F32转换为identity，get_thread_range返回固定std::pair，无堆容器。当前张量连续、同形，走该分支；未发现正常路径new/malloc/throw或日志调用。
7. `ggml_barrier`使用原子和CPU relax；owner亦执行ith0同算子，所有参与者完成后owner做结果校验、checked pool stop/join、ctx释放，最后由graph_probe_main打印report。

## 日志与异常路径不能遗漏

- ggml-impl.h固定`GGML_DEBUG 0`，worker pause/wait中的GGML_PRINT_DEBUG被编译为空。当前note也不打印，所以正常算子/调度没有本库显式日志分配。
- 断言失败仍走ggml_abort→stdio/backtrace/abort，不是可捕获C++异常。binary-ops有shape/type断言，不能把“正常无throw”描述成“任何输入都不会异常结束”。
- 通用ggml_log_internal_v（ggml.c:197）格式化超过127字符会calloc，然后调用全局log_callback；该callback若换成C++抛异常实现，可能从调用它的任何worker传播。此次正常路径没触发，但全局回调配置仍是可信边界。当前logger不能作为“无分配通用日志”承诺。
- pthread_mutex/cond/线程退出、C11原子底层、stdio和目标libc行为未在本地源码范围完整验证。当前池通过stop+join退出，不主动pthread_cancel；不能据此断言目标pthread实现永不使用unwind/cleanup机制。
- single-thread libgcc是否正确支持多个线程中的异常状态/TLS、静态初始化guard或栈展开，不由本图成功证明。一个owner正常初始化成功后多个worker执行不抛路径，与并发throw/catch是不同验收项。

## 更广泛llama不能直接承诺owner-only可抛API

源码存在明确扩展入口：extra tensor_traits的virtual get_tensor_traits/compute_forward/work_size、MAP_CUSTOM1/2/3及F32映射函数指针、全局log callback、pool note hook。这些回调/扩展可能由worker调用，不能仅在最外层安排一个owner就改变执行线程。`ggml_graph_compute_thread`的abort_callback虽仅ith0调用，也不意味着其他回调均owner-only。

CPU backend ggml-cpu.cpp另外有plan/work_data new/new[]（113/119/156）及context/backend创建（196/208）；这些通常由驱动owner触发，但本次直接ggml_graph_compute绕开它们，没有审核完整llama scheduler/loader/量化/所有算子生命周期。其他扩展首次懒初始化和kernel内部是否分配，需逐个选定模型/算子/配置再审，不能用本MUL结论替代。

若未来采用“只有owner能调用可抛API”的限制，必须：冻结明确算子/扩展白名单；owner完成全部可达懒初始化与工作区分配；禁止/审核worker可达自定义、日志和note回调；验证实际目标对象调用及运行期间worker分配/throw钩子。仍要单独处理其他应用线程和异常runtime的全进程契约，不能把多个模块各自single-owner当全局唯一异常线程。本次没有完成这些条件，因此对完整llama的严格owner-only声明给出**未证明**。

## 本次交付边界

只读app/k7graph及其固定vendor里上述有限调用链，未全仓扫描、修改代码或使用SDK/硬件。inputs.json记录读取源码SHA；未编译、运行或抓取目标链接结果。最终目标宏、链接对象、异常库构建选项及实测镜像对应仍由主代理核对。当前2/4小图正常路径可按上述条件说明；不能标记并发异常验收通过。

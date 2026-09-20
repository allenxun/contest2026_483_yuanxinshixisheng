# NuttX 嵌入接续（未构建或运行目标）

源：graph_probe.c + graph_probe_main.c；C11，include 路径 input/include/；目标不要定义 GP_HOST_MAIN 或 GP_TESTING。导出 C 入口 velavision_graph_probe_main(int,char **)，可作为主会话已有诊断应用的显式子命令调用，或由其 NuttX builtin 注册；不要随无线服务启动自动执行。这里没有修改正式 CMake/Kconfig/builtin。

链接主会话完成门禁的真实 ggml-base、ggml-cpu checked 实现及所需 C++ runtime/pthread/math 依赖。必须存在 ggml_pool_create_checked、ggml_pool_destroy_checked 和 ggml_pool_required_bytes；禁止用 upstream threadpool_new/free 替代。input/include 是固定 b5046 头与 checked 头快照，不应从其他 llama 版本混用。host run_tests.py 链接的是独立 pool-safety 既有 MinGW 真库；这些 x86 库不能链接 ARM64。

入口接受 graph_probe [2|4|both|cleanup]；默认 both。静态 gp_state 位于 BSS，包含128KiB graph arena及4KiB plan scratch，不放任务栈。建议主会话独立 RAM 诊断镜像显式启动并记录真实返回值、栈峰值、CPU计数和无线并发证据；本候选未指定亲和性，未接入 affinity-v1。

每辅助线程请求256KiB pthread栈，2/4线程包括调用者。四线程池准入上限1MiB（元数据+请求辅助栈），还需额外 gp_state、调用者栈、C++/ggml全局表和系统分配开销；这不是整应用1MiB上限。当前MinGW每次context使用50928字节、plan_work为0。NuttX实际栈、TLS、调度及内存基线必须另测，不能直接照主机数值验收。

owner为单线程同步执行；入口 atomic_flag 拒绝重入。gp_run 不带硬截止时间；ggml_graph_compute、pthread_join 可能阻塞。主会话要用独立监督任务观测，超时不能释放仍可能使用的 arena/context/plan/pool/hooks。cleanup 只能在确认图调用已返回后由单owner执行；失败会保留全部相关对象。若强杀执行任务，入口锁/库锁/运行线程可能残留，不能把再跑cleanup称为安全恢复。必要时由主会话采用受控重启/独立进程级隔离策略；本代码未实现线程强停。

上游 ggml_init 的小型 context 仍通过 GGML_MALLOC 分配，某些算子/graph API仍有 GGML_ASSERT/OOM abort。这里预先限制固定图arena，但没有修复上游全库 OOM。测试阶段停止是明确注入的错误返回，不等同于真实 allocator 故障被可恢复处理。

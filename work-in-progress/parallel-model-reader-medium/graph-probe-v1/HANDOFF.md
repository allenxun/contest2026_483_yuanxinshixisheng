# 零模型权重 CPU 张量图探针交接

独立候选完成，仅写 graph-probe-v1/。未改旧候选/正式源码/SDK/VM/中央日志，没有访问COM8/板子、设备节点或模型。基线 llama.cpp b5046 / 74d4f5b041ad837153b0e90fc864b8290e01d8d5，真实checked线程池来自parallel-llama-pool-safety。

## 实现与结果

graph_probe.[ch] 是 C11 API，graph_probe_main.c 是可嵌入NuttX C入口。使用真实ggml_init、ggml_new_tensor_2d、ggml_mul、ggml_new_graph_custom、ggml_graph_plan与ggml_graph_compute；直接使用CPU图API，不需要llama模型API或权重。A[i]=i%17-8、B[i]=i%7+1，64x64 F32逐元素乘法，逐项独立整数公式比对4096结果；已知checksum=-10。不是矩阵乘法、量化推理或模型加载。

显式checked pool，2/4线程均包含调用者。hook只观察真实辅助worker进入compute事件，预期掩码2/14，主调用者编号0没有计入此hook。gp_run同时核对结果和worker掩码；主机正常两模式启动/退出辅助线程分别1/1和3/3，pool bytes/handles/running/mutex/cond/attr均归零。没有调用或伪造ggml_threadpool_get_n_threads。线程配置、worker索引和事件证明实际辅助线程执行过图，**不证明它们运行在两个/四个物理核或A72**。默认无绑核，未集成affinity-v1。

每个gp_state保有pool/context/cplan/hooks和对齐arena，单owner且不可复制。计算返回后先checked destroy池，确认回收成功才ggml_free context；join等清理失败时连同graph arena/plan一起保留，拒绝新gp_run，供gp_cleanup重试，绝不提前释放或丢失指针。初始化只对全新存储调用，不能对待回收对象memset。

## 主机测试

run_tests.py 使用 MinGW gcc/g++ 12.2、C11 -Wall -Wextra -Werror -pedantic -O2，生产和测试对象分开构建；仅新增文件重新编译，固定旧真库只读链接。生产入口both两模式执行通过；20个独立子进程分别覆盖每种线程数的正常、pool分配拒绝、辅助线程创建失败、创建失败叠加join拒绝、四个图构造阶段停止、真实计算后结果损坏检测、正常计算后join拒绝并重试回收。图阶段停止/错误结果及pool hooks都是显式注入，未替代计算核或伪造成功pthread操作。

原始命令、退出码和输出在evidence/host-tests.json。scenario3在线程数2时首次create即失败，因此没有存活线程可触发join保留；线程数4时确实保留已创建池并重试清理。scenario9两模式均在真实图后保留context/pool，然后真实join释放，测试断言资源归零及开始/退出相等。

首次编译漏复制ggml-alloc.h已保留在attempt-01-missing-header.json；复制固定原始头后完成重新编译。没有隐去该构建失败。链接/编译每步30秒，其余每子进程15秒；Python超时会终止该主机测试进程，不意味着板端线程可安全强杀。NuttX阻塞、回收及OOM边界见NUTTX-INTEGRATION.md。

context_used=50928、plan_work=0；128KiB固定图arena和4KiB scratch。请求池预算：2线程263552字节、4线程788928字节，含请求辅助栈、不含全应用开销。MinGW静态stack usage中gp_run自身1360字节；不含库调用链、printf、TLS/中断，不能当目标栈峰值。

## 追溯与接续

evidence/input-hashes.json记录固定源、测试/header和实际链接库的输入哈希；input/include是逐字快照；delivery.json为本目录逐文件哈希。source和旧库原始构建对应关系来自旧pool-safety交付记录，本轮没有重新构建库或宣称覆盖其全部对象测试。

主会话负责现有ARM64对象/完整链接门禁与本新增应用的集成、NuttX真实运行、栈/资源和CPU归属测试。该候选未改变主会话已报告39个ARM64对象/独立链接门禁的范围，不把本主机执行记作目标验收。

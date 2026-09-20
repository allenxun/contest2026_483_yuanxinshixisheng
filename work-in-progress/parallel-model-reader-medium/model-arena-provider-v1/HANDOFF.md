# K7 模型池 provider / 小额 tensor 诊断候选

独立候选完成，仅写本目录。先逐字冻结正式rk3576_model_arena.c与k7_model_arena.h后实现；input/保存真实源码/API及上轮已冻结buft。没有目标运行、SDK/VM/串口访问、模型或KV接入。

## 真实目标接口映射

k7_target_provider.[ch]严格调用四个现有API：k7_model_arena_initialize()、k7_model_alloc(size_t)、k7_model_free(void*)、k7_model_available()。initialize的原始0/负NuttX errno保存在initialize_status并由kap_initialize原样返回；诊断入口将初始化失败映射为非零EIO，同时打印init_raw，不假装初始化成功。未初始化不能分配。

固定目标头定义base=0x60000000、size=0x40000000，64字节对齐来自真实mm_memalign(heap,64,bytes)。provider只接受alignment==64，bytes必须为64倍数、单次/累计最多1MiB；最多8个所有权槽，先找空槽再申请。buft同时配置单buffer/累计1MiB，双层拒绝都无普通heap fallback。分配后检查64对齐和完整地址区间；差值算法避免address+bytes溢出。

每个成功申请原始pointer/size记录在provider槽；release只允许完全匹配、valid槽，调用k7_model_free原指针一次，再清槽。外来地址、尺寸不符、双release不调用目标free。不能复制provider状态或在存活分配时重置；type/ctx生命周期遵循已冻结buft合同，provider保持静态存活。

真实k7_model_free内部直接mm_free、不检查域。因此若k7_model_alloc异常返回越界/错位地址，本adapter不会把它送回free冒险，而是记录quarantined槽、失败关闭后续申请/再初始化。这不是“已回收”：报告live/quarantine和非零错误，保留原指针待主会话诊断，不能重置状态抹掉资源。void free也不提供回收结果，诊断额外比较available前后；发现未回基线便阻止后续复用。该差异也可能来自其他arena使用者，不自动判定allocator泄漏。

## 小额无权重诊断

k7_arena_diagnostic.c使用真实ggml API创建两个64x64 F32 tensor（no_alloc metadata ctx），通过冻结K7 host buft分配payload，逐64元素调用tensor_set/get并核对8192项。每tensor payload地址和完整长度做arena范围/对齐检查。释放顺序是aggregate buffer -> ctx -> buft；type若异常不能销毁保留在provider.retained_type，不丢失指针。失败ctx直接丢弃，避免旧ggml分配失败留下的tensor地址被复用。

正常payload只有32768字节；32768字节metadata放静态BSS，输入/输出各64float位于任务栈。最多1MiB是provider申请上限，不是本次常规诊断大小，也不包含ggml小元数据/C++ wrapper/线程runtime等普通heap开销。该诊断不创建线程池、不计算图、不加载权重，不扩大到KV/scratch/output/tokenizer。

导出C入口velavision_arena_provider_main(argc,argv)，不接受额外参数，static owner锁拒绝重入；直接调用kap_diagnostic同样要求全局单owner，因为metadata静态共享。锁只覆盖此入口，不能阻止k7mem或其他arena客户；主会话需安排独占测试窗口，才可解释available_before==after。

## 目标编译接入清单（未执行）

1. 核对当前目标镜像真正包含arena映射/初始化实现，确认实际头/实现哈希与input-hashes；不匹配先评审，不能静默替换。
2. 新增k7_target_provider.c、k7_arena_diagnostic.c、k7_arena_provider_main.c和input/buft/k7_host_buft.cpp；C11+C++17、现有异常runtime、固定b5046 ggml真实目标库。不要定义KAP_HOST_MAIN，不要添加host-mock路径。
3. 使用实际NuttX k7_model_arena.h与固定b5046头。input/arena/rk3576_model_arena.c只是证据，**不要把它和目标既有同名实现重复编译**。本目录input/include为固定ggml header，内部ggml-backend-impl.h不能跨版本混用。
4. 注册显式诊断入口或由主会话诊断应用调用；不随无线/模型服务自动启动。记录init_raw、before/after、peak、8192 checked、mismatches、range、returned以及live/quarantine。
5. 成功要求初始化0、全部值一致、范围正确、原指针释放配对、无隔离/错误、arena可用恢复；目标栈峰值/可用量由真实运行给出。本主机结果不可替代板测。

## 主机测试与边界

run_tests.py共20条命令通过，gcc/g++12.2，C11/C++17 -Wall -Wextra -Werror -pedantic -O2。编译/链接每步30秒、运行15秒。target-header-shape-only.o仅在Windows按真实目标header编译检查API形状，**不是ARM64对象且未链接/执行目标API**。

其余测试使用host-mock/nuttx/mm/k7_model_arena.h：包含冻结声明后，仅在主机把BASE/SIZE重定向为1MiB静态数组，链接mock的四个arena API。ggml及K7 buft仍是真实冻结代码/库；mock只是接口协议与失败注入，不代表NuttX mm实现。input的正式头和源码未改。

正常入口和mode0：32768字节payload、8192项零错、1次申请/1次释放，mock可用1048576->1048576。mode1原始initialize=-ENOMEM且无alloc；mode2申请OOM返回且基线恢复；mode3/4错位/越界保留1隔离槽且不调用free；mode5 mock free故意不归还，基线检测失败；mode6超1MiB/错误alignment在API前拒绝；mode7精确1MiB边界与累计超额、配对释放；mode8尺寸错误及double release不会调用目标free。

wrong-address测试有意保留mock资源到测试进程退出，不能写作“所有失败均释放”；真实目标若出现这种情况需要主会话诊断。没有CPU/DDR/DMA/缓存一致性或长期测试结论。上游ggml_init元数据OOM可abort，其他ggml异常也未统一转为C错误；目标任务不能靠硬杀就宣称安全回收。MinGW kap_diagnostic静态栈估计864字节不含库调用链，目标栈仍待测。

## 交付

evidence/host-tests.json是原始命令/输出；evidence/input-hashes.json列正式API、冻结buft、头/库输入；delivery.json逐文件哈希。上轮buft的size=0 dummy引用寿命、外部串行与未覆盖路径仍适用；本诊断不改变正式源码和当前graph-core状态。

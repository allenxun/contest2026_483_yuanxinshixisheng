# 1GiB模型池接入固定b5046的实施审计

结论：**不能只把ggml_init的mem_buffer改成模型池，也不能只设use_mmap=false。** 最小权重接入是新增显式K7 host buffer type（专用alloc/free），再通过已有tensor_buft_overrides让全部权重选中它。KV、scheduler graph buffer、CPU work_data和output各自另有分配点。普通堆继续承载有界元数据/STL/runtime/线程管理，绝不全局替换malloc/new。

范围：只读正式arena/app代码、固定b5046源码及既有reader/integrity。唯一输出model-arena-plan-v1。未改graph-core输入、正式源码、SDK或硬件；无模型下载/复制。证据是静态路径审计与小型主机所有权辅助器测试，不是Qwen加载或目标内存验收。

## 当前arena真实接口

port/new/nuttx/include/nuttx/mm/k7_model_arena.h:6-16给出base=0x60000000、size=0x40000000，即[0x60000000,0xa0000000)，CPU-only且不属于malloc/USB/NPU DMA。rk3576_model_arena.c:11 initialize用专属mm_initialize并以mutex+atomic发布；:26 alloc用mm_memalign(heap,64,bytes)；:32 free用该heap的mm_free；:38 available是mm_mallinfo.fordblks。

初始化不等于整个1GiB可全额申请：堆管理开销、碎片、其他使用者均消耗空间。available是瞬时总空闲，不是最大连续块，也不是预算保留事务。alloc未初始化/零长/失败返回NULL；free没有域检查、没有状态返回，必须严格保有原始指针所有权，不能传偏移地址或普通heap指针。app/k7mem使用384MiB稀疏页测试，free_before==after，只覆盖该诊断分配，不证明模型及KV并发可放下。rk3576_boot.c:109-111有条件MMU映射；本审计不验证当前RAM固件是否启用或初始化。

## 分配、所有权与释放配对

行号均针对固定b5046（完整输入哈希在evidence/input-hashes.json）。

| 类别 | 实际分配路径/当前域 | owner与释放 | 最小接入/边界 |
|---|---|---|---|
| 权重F32/量化tensor payload | llama-model.cpp:3887 -> ggml_backend_alloc_ctx_tensors_from_buft；ggml-alloc.c:984计算tensor布局；ggml-backend.cpp:1938默认ggml_aligned_malloc | model pimpl->bufs是ggml_backend_buffer_ptr（:369）；ggml_backend_buffer_free -> iface.free_buffer -> 默认aligned_free，随后delete wrapper | 新K7 host buft用k7_model_alloc，自己的free_buffer只调用k7_model_free；tensor_buft_overrides `.*` 指向该类型（:1581）。禁止返回默认拥有型CPU buffer后直接让其aligned_free处理arena地址 |
| mmap权重 | llama-model.cpp:3866分支从mapping host ptr建立borrowed backend buffer；llama-mmap.cpp管理mmap/munmap | mappings owner持有映射，borrowed buffer不拥有payload | 首版明确use_mmap=false/use_mlock=false。默认model params在:12356为use_mmap=true；参数关闭不移除编译平台mmap符号 |
| KV K/V tensor payload | llama-kv-cache.cpp:79-111：offload=false仍选ggml_backend_cpu_buffer_type；alloc_ctx_tensors_from_buft | KV bufs vector的ggml_backend_buffer_ptr释放；ctxs独立持有tensor元数据 | 显式向KV构造/初始化注入K7_KV buft；权重override不作用于这里。按实际每层n_embd_k/v_gqa、kv_size、type_k/v和alignment预估后实测，不把Q4权重精度当KV精度 |
| 图激活/中间tensor payload | llama-context.cpp:223-280选择backend_buft并创建scheduler；sched_reserve -> gallocr buffer分配/扩容 | context sched拥有gallocr；ggml_gallocr_free(:419)逐个backend_buffer_free；reserve可能替换旧buffer（:770） | 给CPU scheduler的backend_buft明确选择K7_GRAPH。预算含reserve峰值/重分配过渡，失败不能退回普通大heap |
| CPU算子work_data | ggml-cpu.cpp:155-156 new[]，backend结束:100 delete[]；显式plan版本:119 new[]、:135 delete[] | CPU backend/CPU plan分别拥有scratch | 独立allocator pair或专用buffer owner；同时修改grow/free和plan create/free，分配新区成功再交换，不能只改一处new[]留下delete[]。该分配不会被host buft自动接管 |
| logits/embeddings输出 | llama-context.cpp:1480 output_reserve，:1524-1531默认CPU buft | context buf_output unique owner，reset/free旧buffer | 以实际n_outputs、n_vocab、n_embd核算；超普通heap预算时显式K7_OUTPUT buft；不假定这是小分配 |
| tensor元数据/graph元数据 | model.cpp:1450附近ggml_init(no_alloc=true)；KV:51同类；context.cpp:250 buf_compute_meta.resize | ctxs unique owner -> ggml_free；vector按其allocator释放 | 默认保留普通heap但必须限tensor/node/cell等数量。no_alloc=true只把payload延迟到backend buffer，metadata依然分配；把ctx放arena不是权重接入 |
| tokenizer/vocab/GGUF元数据/regex/maps/strings | gguf.cpp parser以及llama模型/词表STL对象 | C++ RAII、gguf_free、STL析构 | 暂保留普通heap，先限制GGUF数组/字符串长度与模型规模再记录峰值。不能无依据称这些全部很小；总vocab可能显著 |
| 同步host权重读取 | loader.cpp:1031-1034 host buffer分支直接read_raw(cur->data,n_size) | 目标payload属于权重buffer；不需要整tensor临时vector | K7 buft必须is_host=true且CPU supports_buft(:436)接受；将read_raw拆为<=reader.max_read的有界块并用mi_read写入目标，不复制完整模型到heap |
| 非host上传临时区 | loader.cpp:899的read_buf；:1061 resize(n_size)；异步分支4x1MiB host staging/event/backend | 局部vector + 手动清理host buffer/events | 首版CPU-only直接host路径，明确拒绝走非host/GPU分支。check_tensors可能启动std::async，另设同步校验路径/禁用且解释，不能让逐tensor线程爆发 |
| runtime/checked线程池/线程栈 | ggml和C++ runtime以及checked pool自身分配 | 原分配器配对，pool checked destroy/join | 普通域预算保持独立。新pool不能借用权重arena raw指针进行普通free。计算未停/未join时保留所有引用，禁止释放模型/graph/KV |

## 最小补丁范围与明确接口

1. 新增例如ggml_backend_k7_buffer_type(domain)（名称是提议，尚未实现）。它是显式host类型，alignment至少满足固定CPU TENSOR_ALIGNMENT及k7的64，alloc失败返回NULL而不fallback；get_max_size基于配置域上限，实际申请仍检查累计quota和k7_model_alloc结果。weights/KV/graph/output可用不同domain对象计账，共用1GiB物理heap。domain及锁/计数需活过所有buffer，包括上游size=0探测buffer。
2. 最窄实现可在ggml-backend.cpp相邻CPU buffer实现处增加专用buft/iface，复用CPU memcpy/get/clear逻辑，**独立free_buffer=k7_model_free**；或独立源引用ggml-backend-impl.h实现。这是内部ABI，固定提交不能跨版本。ggml_backend_buffer_init:88的wrapper用new，可能throw；alloc取得arena块后构造wrapper失败必须先k7_model_free再返回错误/传播，不能泄漏。quota修改也必须回滚。
3. 首版不必改model权重选择器：llama_model_params.tensor_buft_overrides接受{pattern=".*",buft=K7_WEIGHTS}和{NULL,NULL}终止。这条覆盖绕过默认select_weight_buft，并引入regex分配；将选择结果逐tensor/ctx审计，不使用非host/repack/CPU extra类型。use_mmap=false避免mmap-host替换逻辑。n_gpu_layers=0只是配置意图，仍须检查所有actual buffers是K7 host。自定义buft支持CPU并不证明所有扩展算子兼容。
4. KV需改llama-kv-cache.cpp选buft点及传参（或清晰的平台显式策略），graph需改llama-context.cpp backend_buft列表，output改output_reserve，CPU work_data改ggml-cpu.cpp两类owner的alloc/free/grow。不要把默认CPU buft全局切换后失去分配类别账本。
5. loader文件接口需要另一个小而完整的改造：metadata parser、分片和tensor读取全部绑定已验SHA的同一mi_model对象；见下节。上述allocator补丁不能解决文件读取资格。

## 同句柄读取差距

冻结loader.cpp:470先gguf_init_from_file(fname)，gguf.cpp:705内部fopen/parse/fclose；loader随后:478另建llama_file(fname,"rb")。分片:529/:546重复同样两次打开。llama_file非Windows用ftell/fseek(long)/fread，缺现有reader的长度预算和失败关闭语义；mmap还能绕过有界read。

mr_open检查普通文件/精确长度，但POSIX默认ENOTSUP、真实挂载/off_t尚待验证。integrity-v1 mi_verify_open消费已打开句柄，流式SHA后恢复原偏移并READY；它不是FILE*也没有已实现GGUF reader适配。**不能验完mi_model再调用现有llama_load_model_from_file(path)，那会重开路径。** `dup/fdopen`即使共享文件描述也不自动继承mi_read的界限和READY撤销策略，且GGUF现有API不暴露已验证reader。

建议增加GGUF有界reader接口(read_exact/seek_absolute/tell/length)并由mi_model提供，实现与原parser同一逻辑而非另外粗糙GGUF解析器；llama_file只读构造接收移动/独占的mi_model而非路径。每分片都有独立可信长度+SHA manifest、普通文件资格、同句柄metadata/tensor读；未知分片或超过总预算直接拒绝。mi_read单次预算小于tensor时循环，先做offset/size范围校验且失败销毁未完成model。禁mmap/mlock真实能力路径，不提供假成功。

同句柄仍不保证同长度内容不被外部写者改变；integrity测试已复现。验证起到最后一次加载读取都需要不可变挂载/排他写保护。成功把所有权重复制到arena后才可关闭对应文件；模型生命周期结束再释放arena payload。SHA通过不等于GGUF结构安全，结构/数量/offset与tensor大小算术仍需检查。

## 可执行接入清单/验收门禁

1. 主会话确认当前镜像实际K7映射/初始化，记录普通heap和arena可用；停止其他arena诊断分配者（例如k7mem test），无需本审计重测硬件。
2. 实现新buft并先做1..4096字节真实目标分配/写读/配对释放；零长探测、预算拒绝、分配失败、wrapper new失败、双关闭、缓冲析构和并发quota测试；连续失败后available恢复基线。
3. 用无权重小图在K7 buffer承载tensor；所有payload地址必须位于arena，普通heap仅允许观测到的metadata开销。先禁CPU extra/repack，检查未误用aligned_free/delete[]。
4. 固定可信Qwen GGUF来源、revision、长度、SHA与分片，不在此审计填猜测值。执行同句柄SHA+metadata读取，限GGUF数量和普通heap峰值；没有可用普通文件挂载或写保护即停止。
5. 建立实际预算：W=sum(真实tensor alloc_size+alignment/duplication)、K=真实各层K/V布局、G=scheduler reserve高水位、C=CPU plan scratch高水位、O=output最大值，另留碎片/管理余量R；检查W+K+G+C+O+R <= 独占准入额度且单个连续块可申请。1GiB总空闲不保证单块成功；禁止将1GiB标称值当available。普通heap另算元数据/tokenizer/runtime/线程栈峰值，不混账。
6. 分阶段验证weights-only完整读入/逐项地址审计 -> KV小n_ctx -> graph worst-case reserve -> 单步decode；每阶段失败按真实owner回收且不得自动回退普通大heap。记录所有分配域与peak，不用模型文件大小推断总运行RAM。
7. 完成后才讨论n_ctx/n_batch放大与多线程；graph-core当前硬件工作由主会话负责，本审计不写其输入或推翻版本边界。

## 小范围独立验证辅助器

arena_buffer_lease.[h/cpp]只证明 `k7类配对分配 -> ggml_backend_cpu_buffer_from_ptr borrowed wrapper -> wrapper销毁 -> 专用release` 的所有权顺序。它不是selectable buft、不能直接接入loader。其返回wrapper的buft是CPU_Mapped，**不能取该类型放进tensor_buft_overrides**，因为该类型的alloc_buffer仍是默认CPU普通heap分配。

主机test_lease使用固定小型64对齐数组模拟arena provider，真实ggml wrapper执行clear/get/free，验证预算前拒绝、provider失败、错位回滚、busy保护及幂等释放；没有访问或模拟成功调用实际k7 DDR。wrapper new抛异常的catch清理已编码，但本测试未注入真实new异常，不列为通过项。没有替换任何全局malloc/new/free。需保持C++异常运行库可用；helper的alloc/release回调不得抛异常。

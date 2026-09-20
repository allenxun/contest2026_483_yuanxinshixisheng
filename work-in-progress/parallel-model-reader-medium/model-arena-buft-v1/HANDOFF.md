# 显式 K7 host buffer type 候选 v1

独立最小候选；只写本目录。固定 b5046 API，未改正式代码/旧候选/SDK/硬件，不含模型/loader或权重。

k7_host_buft.[h/cpp] 提供真正可选的ggml_backend_buffer_type_t。它的alloc_buffer回调向显式provider申请payload；get_alignment/get_max_size/is_host真实返回配置，非空分配成功后buffer->buft指向该类型。默认ggml_backend_cpu_buffer_type、malloc/new/free均未替换。内部引用ggml-backend-impl.h，严格固定版本ABI。

## 所有权和预算

创建类型只在普通heap申请小domain对象。provider提供非抛异常allocate(context,bytes,alignment) / release(context,原始指针,bytes)配对，payload不会交给普通free/aligned_free/delete。回调须满足可信所有权契约、返回足够长度的CPU可访问内存，provider的ctx必须活过所有buffer。

bytes按指定alignment向上取整并检查SIZE_MAX溢出；alignment必须是2幂、至少当前CPU API要求且不超过4096，max_buffer是正的alignment倍数，不能大于total_budget。配置预算是该类型**所有存活非零payload的累计填充字节**；用差值检查剩余额度，拒绝超限且不fallback普通heap。live/peak字节不含domain、ggml wrapper、tensor元数据或provider管理开销。各类型若共用K7物理heap，仍须provider/上层统一全局准入，不能把每类1GiB相加。

provider成功后检查返回地址对齐；不合规就按原配对release回滚。真实ggml_backend_cpu_buffer_from_ptr创建borrowed CPU wrapper，保留CPU set/get/clear/copy接口，随后装入本类型与独立owning free callback。构造new异常/NULL时先release原payload，成功才增加计数。释放先调用该provider release，减少账本；ggml核心随后delete小wrapper。普通allocator永远不拥有provider payload。

所有分配/释放、type销毁和stats调用要求外部串行化；未实现共享锁或并发quota。计算线程可以按正常ggml合同访问tensor，但必须在owner确认使用者静止之后释放。不能直接更改内部buffer尺寸、buft或context。

k7_buft_destroy对存活非零buffer返回EBUSY。类型和provider仍必须活过所有引用：b5046 ggml_backend_buft_alloc_buffer(size=0)绕过自定义回调直接建dummy，因此本候选无法计数零buffer引用。释放所有零dummy、模型/scheduler引用后才能销毁type；目标建议让type具有诊断/服务全生命周期。此限制明示在头文件，不能把EBUSY检测称为完整引用计数。last_error只对应本类型最近一次非零alloc回调，不代表上游绕过路径的状态。

## 使用与目标接入

初始化k7_buft_config：provider绑定真实k7_model_alloc/free，alignment=64，显式max_buffer_bytes与total_budget。真实provider适配需要先k7_model_arena_initialize成功；allocate只接受其保证的64字节对齐，调用k7_model_alloc(bytes)，release只调用k7_model_free(original)。这个目标适配尚未写入或编译，不能将主机fake provider当目标DDR实现。

调用k7_buft_create(&config,&type)，检查返回；然后可把type传给ggml_backend_alloc_ctx_tensors_from_buft或既有llama tensor_buft_overrides。当前type.device=NULL沿用CPU host模式；真实主机CPU backend supports_buft确认接受。

不要把本次通过等同于已运行llama loader：仍需use_mmap=false/use_mlock=false、普通文件+SHA同句柄读取、权重预算和结构校验。未覆盖KV buft选择、scheduler backend_buft、CPU work_data new[]/delete[]、output_reserve、GGUF/tokenizer/STL/runtime元数据。这些仍可能使用普通heap，接续上次model-arena-plan-v1/HANDOFF.md的独立路径。

## 真实主机验证

run_tests.py用MinGW g++12.2，C++17 -Wall -Wextra -Werror -pedantic -O2，链接固定pool-safety旧ggml.a/ggml-cpu.a/ggml-base.a。生产对象、生产EXE、带唯一wrapper异常注入的测试EXE分开构建；生产对象不含注入API。每次编译/链接30秒，其他子进程15秒。evidence/host-tests.json保留完整命令、输出、返回码；7条命令通过。

provider是明确fake的8个256字节对齐数组块；**没有调用实际k7_model_alloc或访问目标地址**。真实ggml执行：host支持查询、直接两个buffer（请求65/129，实际配额128/192）、累计预算拒绝、SIZE_MAX对齐溢出、busy销毁、clear、零dummy、三tensor多buffer set/get/整体销毁。provider OOM、错误对齐、真实ctx分配第二块失败、第三块预算失败均释放已成功分配payload，live_buffers/live_bytes回到0。测试构建在provider acquire之后抛一次std::bad_alloc，证明wrapper失败catch回滚；这是明确注入，不宣称触发真实系统OOM。

首次测试误把CPU最小对齐固定假设成64，配置32没有如预期拒绝，已保留attempt-01-test-alignment-assumption.json。测试改为从真实CPU API取得最小对齐再构造非法值，产品实现自始使用真实API。K7 provider仍建议配置其实际保证的64。

上游ggml-alloc.c部分分配失败会释放buffer却留tensor->data旧地址；本测试在NULL后立即丢弃整个ctx，不复用失败ctx。上游metadata realloc未判空、ggml_init的GGML_MALLOC abort以及multi-buffer wrapper的new异常仍未修复；这里的provider/wrapper失败测试不能覆盖所有ggml异常清理。外层完整loader仍需其独立审查和失败销毁策略。

## 交付

input/include逐字复制固定头，evidence/input-hashes.json包含来源及实际链接库哈希；delivery.json逐文件索引。没有patch旧vendor；所有改造封装在新源文件，目标集成由主会话执行。

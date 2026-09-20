# Provider direct v2：单 buffer 诊断修正

修正已完成，旧model-arena-provider-v1保持冻结。新目录唯一实质产品代码修改是k7_arena_diagnostic.c；provider、buft、main、头及mock沿用逐字快照。diagnostic-direct-v2.patch给出相对v1的可审查差异，主会话决定是否应用到staged app/k7arena。

## 改动

原诊断通过ggml_backend_alloc_ctx_tensors_from_buft；固定b5046 ggml-alloc.c:954的alloc_tensor_range即使只成功分配一个buffer，也调用未判空realloc扩展buffer数组，失败可绕过本诊断goto done。

v2不调用该helper。按要求先用静态metadata创建no_alloc context及两个64x64 F32 tensor，再checked创建buft。使用实际buft alignment/alloc_size，确认64对齐、每tensor16384字节，k7_buft_round_bytes检查对齐溢出，再以差值累计并核对1MiB上限和type max_buffer。显式ggml_backend_buft_alloc_buffer分配单个32768字节buffer。

取得base后验证buffer type、可用长度、arena完整范围及uintptr加法上界。逐tensor核对未分配/非view、偏移/长度/对齐，再调用ggml_backend_tensor_alloc放置。该固定API只设置tensor buffer/data并调用init_tensor（本buft沿用CPU wrapper的NULL init），不经过realloc或multi-buffer数组。

分配/放置/校验返回错误仍走buffer -> ctx -> type清理；provider原有异常地址隔离与void free后available核验保留。没有改变实际k7 arena实现、1MiB额度、模型或线程路径。

## 验证

真实固定ggml host库＋原host mock API，21条命令通过：正常入口8192项零错误、1次32768字节申请/1次释放，可用量1048576恢复；原9种正常/初始化失败/OOM/错误地址隔离/free不归还/额度与对齐拒绝/精确1MiB边界/错误release测试全部保留通过。evidence/host-tests.json含真实命令/原始输出。

额外nm -u检查diagnostic.o：存在ggml_backend_buft_alloc_buffer及ggml_backend_tensor_alloc引用，不存在ggml_backend_alloc_ctx_tensors_from_buft或realloc引用。这是新增诊断对象的直接符号检查，不声称整个静态库没有realloc。

单步编译/链接30秒，其他子进程15秒。target-header-shape-only.o仍只是Windows工具链按目标header编译形状，不是目标ARM64编译，也未执行目标API。没有SDK/VM/板端操作。

## 保留边界及接入

本修正**未解决ggml_init自身GGML_MALLOC abort**、tensor metadata分配断言或所有上游OOM。type/domain小分配返回错误、buft wrapper异常回滚是已有候选的有限行为；不能据此宣布整库异常安全。内部元数据先创建可避免这些步骤失败时已有payload，但abort仍可中断当前任务。

继续按v1生命周期合同：单owner、静态metadata、所有引用静止后释放；异常arena地址不送未知指针给mm_free，而是保留隔离。mock地址重定向不证明目标DDR范围可用。目标应使用本目录的k7_arena_diagnostic.c替换staged候选对应源，其他来源核对哈希后保持；不可编译host-mock，不可重复编译input/arena证据源码。C11/C++17与固定b5046头/库、真实arenaAPI版本要求不变。

输入哈希和与v1源匹配检查见evidence/input-hashes.json及seal_delivery.py；未改正式源码/中央日志。

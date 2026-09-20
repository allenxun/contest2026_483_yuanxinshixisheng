# checked pool NuttX affinity-v1 适配候选

交付为独立小适配器和精确接入契约，**没有修改/重写线程池，没有应用补丁**。主机只编译执行 affinity_gate.c 的模拟回调测试；affinity_nuttx.c 未交叉编译、未运行，不能计作 NuttX 亲和性通过。输入锁定和输出哈希见 hashes.json，原始编译/测试输出见 host-results.json。旧 NEON 交付不变。

## 固定范围

- 八核拓扑必须由主代理已审计的目标镜像保证：CPU0无线服务，CPU4..7 A72；CONFIG_SMP_NCPUS=8 只是构建约束，不证明这些核已 online。
- 总线程数1..4，包含计算调用者。映射 ith=0→CPU4、1→CPU5、2→CPU6、3→CPU7。单线程也必须验证CPU4。
- 专用推理 owner 用已初始化并核对返回值的 pthread_attr 设置 CPU4 后创建。不要临时改变无线CPU0服务线程的亲和性；adapter不改变调用者、也不承诺恢复原mask。checked pool的单owner契约继续适用。
- 本版只接收明确的固定映射策略；不能开放任意cpumask/strict_cpu/优先级组合。默认池 ENOTSUP 策略仍保留。若通过现有params启用：只允许normal priority、strict_cpu=true、cpumask恰为前n个连续A72核；否则分配前拒绝。不要仅将 ggml_pool_affinity_supported 改为 true。

## 最小接入位置（固定源码见输入哈希）

1. 在 ggml_threadpool 中嵌入一个 `struct vv_affinity_gate`，不保存栈上gate/ops指针。required_bytes使用sizeof(pool)，会自然计入新增元数据；已有溢出/预算/所有权代码不改。选定目标模式后用 `vv_affinity_init` 初始化；保持非亲和性主机模式原行为。
2. create_checked分配前先用真实current_cpu检查owner==4，失败直接返回；或初始化临时gate调用observe(0,startup=1)，检查返回值（不得把临时gate地址交给worker）。分配后在池内gate再次记录owner。**owner不能仅在创建时验证，图启动前还要再验证。**
3. 原THREAD_CREATE循环中、每次真实pthread_create **之前**：

   ```c
   rc = vv_affinity_attr(&t->affinity, vv_affinity_nuttx_ops(), &t->safe_attr, (unsigned)j);
   if (rc) break;  /* 原循环后已有 if(rc) goto fail */
   /* 原 fault hook + pthread_create + safe_created 累加保持原样 */
   ```

   attr_cpu直接返回真实pthread_attr_setaffinity_np返回的errno值。属性在pthread_create调用期间被实现读取/复制，成功返回后再修改下一线程属性；不对已经运行的pthread做事后绑核。setattr成功不代表实际运行CPU正确。
4. secondary入口，在POOL_RUNNING通知之后、进入任何pending/compute循环之前，用observe(index,startup=1)读取真实sched_getcpu并发布ready。失败只沿已有退出通知路径返回，不执行图。create_checked在线程创建全成功后等待 `vv_affinity_ready`：0才可返回成功；EAGAIN继续；其他errno进入原fail。等待须主代理用MONOTONIC总截止（建议2秒）+有限轮次+短sleep实现，时钟/睡眠错误也fail。不能在ready前把out交付可运行owner。create失败仍走原destroy_checked，不增加第二套join/free；清理失败保留out，禁止计算，原错误与cleanup错误应分别记录。
5. 每次图kickoff **之前**验证owner CPU4及gate错误。失败返回GGML_STATUS_FAILED，不递增n_graph、不唤醒图；保留具体errno/observed CPU用于诊断。不能把该检查放在现有kickoff内部n_graph递增之后。
6. 在 `ggml_graph_compute_thread` 中、`set_numa_thread_affinity` 之后及**函数末尾现有最终 ggml_barrier 之前**，对对应ith调用observe(startup=0)，发现偏离后置gate错误。最终观测不能放在最后barrier之后，否则owner可能先返回而漏读慢worker错误。**不得仅让错误worker提前return**，因为其他worker会在原ggml_barrier永久等待。此最小观察模式让已开始图完成正常barrier路径，再在取ret处用gate错误覆盖为GGML_STATUS_FAILED；不得消费该图输出。该池后续图在步骤5被拒绝，仍由owner在图静止后destroy。固定NuttX策略应禁用另外的NUMA/上游apply_affinity路径，避免第二套mask策略覆盖本adapter。

步骤6是“错误导致结果失效”的检测，不是运行中核偏离时即时停机。若要求任意时刻发现偏离就停止算子，必须单独设计所有参与者协同取消/图前二阶段许可；这超出本次最小adapter，不应伪称已解决。CPU采样也不能证明两次采样间从未迁移。

## 竞态及契约审核结论

上游worker在create之后自行apply_affinity且忽略返回值，存在已经运行、先碰数据后再绑定的窗口；本版使用创建属性消除应用层事后绑定窗口，但仍以startup实际CPU确认OS执行结果。创建期间尚未返回out，单owner不可能合法发布图；n_graph初始0保持不变，startup-ready足以作为初次创建准入门禁，无需重写池队列。owner在CPU4运行期间，辅助线程使用CPU5..7，CPU0不承担图计算。

gate使用C11原子保存ready、首个errno、实际CPU，不增加mutex/cond/线程/动态分配，不改变hooks.ctx生命周期，也不调用用户hook。ready是一次性启动状态；runtime错误sticky，不能清零后继续复用池。`vv_affinity_result`只返回已记录错误，创建准入必须用ready，不能用result把尚未观察视为通过。无效参数返回EINVAL也必须由调用者检查。

原checked destroy可能无限等待join，本适配器**没有修复也没有掩盖该已有边界**。startup等待有截止不等于整个create/cleanup有硬截止。超时不可free存活worker资源；继续遵守保留out/quarantine规则，由owner层有界监督。

`ggml_pool_affinity_supported()`仍应保持false，直到目标分支已完成上述接线、SDK声明核对和实际创建/运行CPU测试。若未来改为true，须明确它只表示编译接入固定策略，实际create仍可能因offline/权限/目标运行CPU不符失败。Windows模拟结果不构成该能力声明。

## 待主代理验证

NuttX宏/头文件/API及errno约定、pthread创建属性实际行为、CPU映射和online情况；含适配器的真实checked池编译/图运行；setattr失败、第k次创建失败、startup错核/超时、runtime错核的整池集成故障注入；所有错误不产出可消费图、cleanup所有权不丢失。主机模拟只覆盖gate与回调返回传播，不覆盖pthread启动/原池清理或图barrier。

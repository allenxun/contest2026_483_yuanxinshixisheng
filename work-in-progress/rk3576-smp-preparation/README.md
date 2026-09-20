# RK3576 SMP 接入准备（未启用）

当前板端仍是已验证的 `emmc-vfs-20260910` 单核固件。本目录为主会话的独立准备材料，不是第二个产品入口。

`topology.h` 按已归档 K7 DTB 的 0..3、0x100..0x103 affinity 提供双向映射，并拒绝未启用或未知核心。`test_topology.c` 覆盖 1..8 核配置、所有低16位 affinity、Aff2/Aff3、非 affinity 标记、越界及空输出。实际编译/执行结果和输入哈希见 `evidence/smp-preparation-20260910/topology-test.json`。这些是主机边界测试，不是 CPU_ON 或真机 SMP 验收。

## 已确认的 SDK/BSP 缺口

- `port/new/nuttx/arch/arm64/include/rk3576/chip.h` 明确禁止非 UP 构建，现阶段保留此保护。
- 同文件汇编 `get_cpu_id` 取低16位；A72 affinity 0x100 不是逻辑 CPU 256。`arm64_head.S` 随后用该值递增每核 idle 栈，跨簇启用前必须修正且拒绝越界 CPU。
- SDK `arch/arm64/include/arch.h` 的默认 `MPID_TO_CORE` 只取 Aff0，导致 A53/A72 相同 Aff0 重复编号。汇编入口与 C 宏必须一致，不能只补一个 C 函数。
- K7 未提供 `arm64_get_mpid`、`arm64_get_cpuid`；公共 CPU 启动依赖前者生成 PSCI 目标。
- SDK `arm64_cpustart.c` 的 `arm64_start_cpu` 在 PSCI 失败时仅打印并返回，`up_cpu_start` 随后仍返回0。不能把这个返回值当作次核启动成功；需要真实次核到达/调度证据及有界失败处理。
- 通用代码已包含 secondary MMU、GIC 和 timer 初始化，但尚未验证 K7 每核执行、SGI、TLB/cache 和跨核锁路径。

## 下一实现顺序

1. 单独实验配置仅允许两颗 A53，补汇编/C统一映射及越界停驻，保持生产配置单核。
2. 在独立构建中检查 CPU_ON 错误传播与次核启动等待上限、每核栈、GIC SGI、timer、共享内存属性。不能通过移除保护宏代替这些工作。
3. 双核诊断先验证两个逻辑核运行、每核计时器、双向 IPI、原子计数和调度亲和性。设置超时及 RAM 单核恢复方案。
4. 完成两核后再考虑一个 A72；八核与驱动并发验收不计入当前结果。

本目录不写 eMMC、不操作云台；没有修改正式 BSP，也没有同步 SDK 或加载 SMP 固件。

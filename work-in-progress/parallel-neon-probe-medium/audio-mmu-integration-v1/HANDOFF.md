# CPU0 只读 MMU 命令集成候选

最小补丁main-integration.patch在原main参数检查及硬件初始化之前分流 `k7sound mmu`。它调用同一i2c_owner.inc的静态owner，不创建第二个音频互斥锁。root将mmu_command.c、command_core.c、mmu_probe.c、snapshot_arm64.c加入既有k7sound构建；配套.h同目录。原MMU parser和MRS snapshot从冻结v1原样复制，不改其支持范围。

命令：`k7sound mmu 0x<本次ELF的xlat_tables> 0x<本次ELF的base_xlat_table>`。两段长度固定81920/4096，页对齐、互不交叠并位于[40400000,48200000)；只接受0x前缀1..8位hex，拒绝符号、空白、溢出、任意MMIO地址。不要使用本目录测试输出的历史地址。

## 固定CPU与生命周期

mmu_command先trylock现有owner，再用真实k7load已采用的pthread_attr_setaffinity_np创建前绑核方式请求**CPU0**、8192字节线程栈、JOINABLE worker。没有改当前主线程affinity，也不依赖未核实的sched_lock语义。worker首尾sched_getcpu必须为0；每次snapshot还记录MPIDR首尾。单CPU affinity是禁止迁移机制，首尾核对是额外失败检查，不以两次CPU号相同代替绑核。

job/result/semaphore始终静态存储。主线程最多等待完成信号1秒，信号后pthread_join成功才读取/打印worker结果、销毁semaphore及unlock。clock/wait/join失败保留owner与静态context，打印held=1，不销毁或重用潜在活跃资源；因此没有栈context UAF。worker在post之后仅返回，无额外业务；pthread_join本身无timeout，依赖该有限结束路径及调度器。这不构成系统级调度失效时的硬实时保证。创建前失败则清理已初始化资源，清理失败保留owner。

worker只做两次MRS快照及最多4次页表读取，不打印、不访问SAI寄存器、不触平台/codec/功放。root无需为此打开音频时钟。read64两次受限：walk先检查整个table页位于参数白名单，command callback再检查每次8字节对齐/范围后才能在已证明identity RAM内volatile读取。参数只提供地址，不能自行证明来源；必须完成下述exact ELF绑定。

mi_execute要求实际TTBR0基址等于第二参数，检查固定CPU0，两次snapshot的EL/SCTLR/TCR/TTBR0/TTBR1/MAIR/MPIDR全部相等，变化即失败；保留两组原值和每级entry/descriptor输出。MP_OK只表示解析稳定，不自动证明identity、Device-nGnRnE或AF=1，需看原字段。两次寄存器快照不检测并发PTE原地修改；本次调用还依赖已核实静态页表无并发改写。owner只排除音频命令，不是全局MMU锁。

## 本次ELF绑定工具

先在主机对**新编译实际将加载的ELF**运行：

`python bind_elf.py <ELF> <verification.json> <exact-sdk-input-dir>`

只读打印JSON和命令，不执行设备命令。工具核验：ELF SHA与成功构建verification一致；AArch64 ELF64 little-endian；config SHA与记录一致且VA48/PA48/20页表/flat RAM配置满足；提供的SDK mmu.c/h、arch.h、BSP源与本轮冻结审查哈希相同；BSP SHA在构建sources中一致。解析实际符号大小及BSS范围，拒绝重叠、非页对齐和越界。按真实`<4QI4x`（PA,VA,size,name,32bit attrs+padding）解析g_mmu_regions，核对页表区域flat NormalRW及SAI flat Device-nGnRnE，输出本ELF专属参数。

工具只检查g_mmu_regions的覆盖唯一性。common g_mmu_nxrt_regions也覆盖镜像BSS且为NormalRW，已冻结mmu.c可核对；SAI不在common镜像区。这里没有声称完成所有潜在动态映射重叠审计。SDK输入哈希绑定是提供的源码记录检查，不能独立证明编译器实际使用那些文件；root需保留exact SDK采集/构建过程及实际RAM加载哈希。若来源变动工具拒绝，不能手动把current_build_identity_proven置真绕过。命令是可信诊断入口，不接模型或语音工具的任意地址输入。

## 已执行验证

run.py：O0/O2 gcc C11/-Wall/-Wextra/-Werror参数与受限执行测试通过，原输出compile/test-O*.txt、命令返回值runs.json。覆盖范围尺寸/重叠/对齐/词法、每次读取范围、CPU非0、前后快照变化、TTBR参数不符、读失败。没有构造OS/硬件成功模拟；mmu_command.c的NuttX线程胶水与ARM64 MRS分支留root实际SDK编译。

test_binding.py对真实归档audio-mic ELF完成结构和来源匹配，并验证旧ELF配audio-marker构建记录会被拒绝。原输出binding-test.stdout.txt，结果binding-reference-result.json，输入路径/hash单列binding-reference-inputs.json。仅作为工具测试，不能据此在新固件使用旧表地址。

本目录inputs.json冻结13项正式/SDK/旧候选输入。没有设备/SDK命令、正式代码修改、AT/PAR/TLB或页表写。运行期Device结论仍不能排除陈旧TLB、别名及另一翻译阶段；不把静态或软件测试结果称为三零相位根因。

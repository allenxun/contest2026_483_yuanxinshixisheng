# llama 独立链接产物布局审计

结论：本地 `llama-link.elf` 在已记录的低地址RAM和保守保留区约束下没有发现布局重叠；原6MiB驻留内存门禁会正确拒绝它。建议主会话为后续独立固件评审8MiB预算，同时保留并加强其余检查。该独立链接产物没有经过本轮bin生成/核验、正式固件集成或启动验收，不能直接据此上板。

输入SHA256 `1ec6625d7f36f76b90af390dbb30d118913d8306fb45fafd6cf0ce99f0b3e1dc`，与 result.json/unwind-audit.json 一致。前者报告5个根入口保留；后者报告2CIE/2323FDE静态通过。这些信息不代表模型推理、文件接口或线程并发验收。本轮固定14份输入哈希于 evidence.json，读取前后再次比对一致；未访问外部SDK、VM或硬件。

## 地址实数

所有区间均为左闭右开，PT_LOAD物理地址和虚拟地址相同。

| 内容 | 地址范围 | ELF文件段长度 | 内存段长度 |
|---|---|---:|---:|
| RX：text/init/vector | 40400000–405fc000 | 0x1fc000 | 0x1fc000 |
| R：rodata/EH/LSDA | 405fc000–40799000 | 0x19d000 | 0x19d000 |
| RW：data/BSS/initstack | 40799000–40b40000 | 0x2648 | 0x3a7000 |

入口和__start均为0x40400000。ARM64 Image头magic为0x644d5241，text_offset=0，image_size=0x740000，flags=10；image_size与驻留内存跨度一致。三个段连续、不交叠，权限分别RX/R/RW，没有RWX；文件偏移与地址满足0x10000对齐同余，filesz不大于memsz且在ELF内。所有ALLOC节均包含在PT_LOAD内。

- ELF磁盘文件：50,932,224字节，含调试信息，不能当raw镜像原样写到入口。
- 从各文件装载段推导raw地址跨度：3,782,216字节，结束0x4079b648；此处仅算术推导，未生成或核对实际nuttx.bin。
- 运行时内存：7,602,176字节，即7424KiB/7.25MiB，结束0x40b40000。BSS和启动栈虽不在raw文件内容中，仍须纳入占用门禁。
- `_edata=4079b648`，`_sbss=4079c000`，`_ebss=_s_initstack=40b28000`，`_e_initstack=g_idle_topstack=40b40000`；data/BSS/启动栈按序分离。启动栈区域0x18000=96KiB；其中g_cpu_idlestackalloc从40b30000开始，符号表大小64KiB，对应8×8192配置。这里只证明链接布局，不证明运行栈峰值安全。
- `_srodata=405fc000`、`_erodata=40799000`精确包住只读装载段，包括异常表；MMU基础DRAM映射来自rk3576_boot.c。最终通用ARM64代码对text/rodata细化权限的实际启动执行，本轮未访问SDK重证。

## RAM、heap和其他区域

固定locale配置为RAM_START=40400000、RAM_SIZE=132120576（126MiB），所以RAM_END=48200000。当前镜像尾到RAM_END间隙为124,518,400字节，即118.75MiB。该数值是理论可用地址差，不是运行时free；实际heap创建起点/对齐和元数据仍需核对最终SDK的arm64_allocateheap.c或反汇编及启动输出。本地构建记录显示链接了该通用模块，但本轮没有取得其源文件。不能把旧模型池版本的free值套用到本镜像。

| 区域 | 本地依据 | 非重叠结论范围 |
|---|---|---|
| DTB/固件保守排除48200000–49400000 | audit_k7_resources.py；board README记录DTB48300000、固件48400000–49400000 | 配置RAM与镜像均不进入；没有读取当前DTB大小或现场搬迁状态 |
| 无线暂存50000000–50200000 | rk3576_boot.c只读映射、uart_load_cxx_unwind.py | 与镜像/配置heap区间/模型池互不交叠；无线文件实际上传另验 |
| loader快照51000000–51400000 | 已有UART loader只读源码 | 同上；不执行该loader |
| 显式模型池60000000–a0000000 | k7_model_arena.h、rk3576_model_arena.c | 1GiB独立CPU heap，与普通RAM区及上述暂存不交叠；不会自动扩展malloc或保证llama分配已路由到该池 |

radio子块源码地址为50000000/50100000/50180000/50190000，均受2MiB窗口约束。历史fastboot暂存起点40c00800高于当前驻留尾，也高于建议8MiB上限40c00000；它却落在后续普通heap地址范围，属于启动阶段临时所有权，不能当作永远不重叠的永久区域。若复用fastboot路线，需证明完成copy/booti后该暂存及U-Boot对象不再被使用，再允许heap回收；当前UART路径不依赖fastboot暂存。类似地，本地文档不能证明所有当前U-Boot动态分配和固件保留表完整。

## 6MiB门禁的有依据调整

正式 verify_neon_file64_image.py 是绑定neon-file64旧版本及构建哈希的验证器，检查所有段memory_end≤40a00000。本产物的内存尾超出该线0x140000=1280KiB，即使推导raw只有约3.61MiB也不能绕过。6MiB是旧候选预算，板级RAM_END实际更远；不可直接删除memsz检查或只改用文件大小。

建议主会话另建新版本验证器/明确版本参数：

1. 明确将**驻留预算**设为8MiB，即所有段结束≤40c00000；本产物距新线仍有786,432字节（768KiB）。这是本次独立候选的有限增长预算，不是硬件可用RAM上限。若集成后超过预算，重新审查，而非自动增长。
2. 同时要求全部段仍位于配置RAM区、入口固定、ARM64头image_size匹配最大mem端、段不重叠、VMA=LMA、权限匹配、文件范围/对齐正确、ALLOC节包含及栈/只读符号一致；所有保守保留区仍必须检查。
3. 可增加镜像尾至RAM_END至少112MiB的**暂定地址余量政策**；本次有118.75MiB，因此通过。112MiB是供评审的保守预算，不是已测得的llama或无线内存需求，也不证明可成功加载模型。应由最终功能预算确认，不能把heap余量政策当运行验收。
4. 保留原有源码/配置/不可变构建报告哈希、异常表审计哈希及**每个PT_LOAD文件字节与实际bin对应位置逐字节核验**；检查bin长度、8字节补齐、CRC与传输窗口。当前没有bin，因此本工具始终raw_binary_verified=false、boot_authorized=false。
5. 重新核对最终集成ELF、启动头、实际MMU、heap起点、所有loader源/目标/快照区，尤其fastboot临时区域生命周期。不能直接对旧版本验证器扩大常量后加载此独立链接产物。

audit_layout.py 实现第1–3项中的离线地址门禁，常量明确绑定本批已冻结配置，没有替代正式hash/bin验证器。运行示例：`python -B audit_layout.py <llama-link.elf> --output <本目录结果文件>`。输出layout_passed只表示其静态约束通过。

## 测试和未完成

test_layout.py的5个测试方法包含真实ELF、上限精确等于末端/少1字节、旧6MiB拒绝、半开区间边界以及10项变异拒绝（入口、文件长度/偏移、段重叠、radio区、heap跨度、栈末端、Image头、RWX、非法对齐）。真实命令/退出码/原始输出在evidence.json，全部通过。没有生成或执行测试固件。

正式模型allocator接入、运行时heap/栈、DTB与U-Boot现场范围、目标bin字节、启动、模型文件读取、推理、并发异常、无线共存均仍待主会话对应版本验证。没有改并发异常探针或其他冻结交付。

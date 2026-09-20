# SAI 单地址运行期页表审查候选

交付 `mmu_probe.c/h` 纯C受限walk与 `snapshot_arm64.c` 的MRS-only快照胶水。目标固定VA=0x2a610000；最多4级、最多4次64位描述符读取。所有表页先验证完整4KiB位于调用方证明的页表区间，并且该区间在DRAM [40400000,48200000) 内；不触RXDR，不做AT/PAR、TLB、页表写、MMU切换或DMA操作。

## 当前构建的精确依据

input/evidence/audio-mmu-input-20260910 保存root提供的exact SDK文件、config、BSP与ELF符号；inputs.json固定15项哈希。旧audio-rx-machine审计仅作历史对照。

- rk3576_boot.c 的DRAM0_S0用MMU_REGION_FLAT_ENTRY(CONFIG_RAM_START,CONFIG_RAM_SIZE,MT_NORMAL|MT_RW|MT_SECURE)；arm64_mmu.h 第256行宏把同一adr给base_pa/base_va。当前config RAM_START=40400000、RAM_SIZE=132120576，末地址48200000。
- arm64_mmu.c 第163–167行，base_xlat_table、xlat_tables是页对齐静态数组；CONFIG_ARM64_MAX_XLAT_TABLES=20、4KiB页，后者大小81920。第604–608行将base_xlat_table的指针直接写TTBR0_EL1，与identity映射相符；calculate_pte_index/allocate页表路径亦直接访问数组。
- 当前ELF 227bd8fad3ffe54208707a99f0248a5ecb5a7d8cb65beda7fb352eb478151bb3：xlat_tables [4066f000,40683000)，base_xlat_table [40683000,40684000)，都在BSS [4066c000,40ae0000)及DRAM flat区内。**这些地址仅适用该ELF；加入探针后的新链接必须重新提取，不能抄给未来镜像。**
- config VA_BITS=48/PA_BITS=48。arm64_mmu.c get_tcr(1)及arm64_mmu.h TCR宏支持本候选的4KiB、T0SZ16、IPS5。memory_attributes槽0=00(Device-nGnRnE)、槽4=ff(Normal)。arm64_mmu.h定义descriptor type、AttrIndx bit2、AF bit10及输出地址字段；候选逐项对齐这些定义。
- BSP早期EL2路径清除继承stage2并转EL1只是启动证据。本探针在EL1无法读HCR_EL2，不声称证明运行期stage2始终禁用。

## 集成接口与限制

root把snapshot_arm64.c与mmu_probe.c一起编译；只在已核对EL1、同CPU/地址空间、页表不并发修改的上下文调用。mp_snapshot_arm64先MRS CurrentEL，仅EL1继续读取SCTLR_EL1/TCR_EL1/TTBR0_EL1/TTBR1_EL1/MAIR_EL1及首尾MPIDR。别将首尾MPIDR相同当作绝对无迁移证明（可能迁走又返回）；调用方需串行化/固定CPU。EL0不能安全调用特权MRS，此入口不对不可信用户态开放。

然后调用mp_walk，read64由root提供。`current_build_identity_proven`必须基于**本次**构建源码/符号绑定，ranges只允许该镜像实际页表数组区间。不要传整个DRAM作为便利白名单。候选没有直接物理地址强转指针的glue；PA→可读VA回调由集成者按新镜像已核实flat映射提供，并再次检查所接收PA范围。该回调不可读任意硬件地址，不能以成功默认值吞错。

固定支持EL1/MMU on/little-endian/4KiB/T0SZ16/IPS48/EPD0=0；DS/LPA2或其他粒度返回Unsupported，不猜表级。TTBR1只报告，不walk（固定target在低VA）；上级权限字段不综合成访问权限结论。1GiB/2MiB block和4KiB page均可解析，L0 block/无效描述符/输出未对齐拒绝。超过白名单的TTBR或下一页表地址在回调前拒绝。

输出应包括snapshot原值与report全部step原始descriptor/entry_pa、output_pa、AttrIndx、对应MAIR byte、AF、identity/device/ngnrne。MP_OK仅表示解析完成：若identity=0、device_ngnrne=0或AF=0，不能宣布MMIO符合预期。AF未置位时这里只报告，不触发目标访问或补AF。

实际页表内存为Device仍不能单独排除陈旧TLB、别名或额外翻译阶段。建议root前后各快照核对核心寄存器稳定，保留两组原始值；不在本组件刷新TLB或修映射。若发现Normal属性，先隔离配置问题；不得把它预先认定为现有三零相位的原因。

## 验证

`python run.py`：gcc C11 -Wall -Wextra -Werror，O0/O2实际通过。测试覆盖四级Device、Normal、错误输出PA、AF0、block、描述符错误、越界TTBR/子表、区间溢出、未证明identity、EL/粒度/MMU/EPD0/DS/大小端不支持、迁移指纹不一致、读取失败。回调测试内断言每次PA只能在模拟4页范围，拒绝情形验证零次回调。

原始编译/执行输出及命令返回值在compile/test-O*.txt、runs.json。初次主机test.c触发misleading-indentation警告已修复；原输出initial-compile-failure.txt保留。ARM64分支未交叉编译、未执行；主机仅验证其非ARM返回Unsupported分支。没有设备、SDK命令、正式源修改或中央日志修改。

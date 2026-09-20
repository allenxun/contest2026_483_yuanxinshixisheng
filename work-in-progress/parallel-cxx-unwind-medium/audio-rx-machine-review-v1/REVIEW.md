# audio-mic RX machine-code audit

审计ELF SHA256 **4b5ab4e9ec2000616e1fe7c25cb83a45b11501253c6469fc5c4c39de3fc93361**，ELF64 little-endian、EM_AARCH64=183、GCC13.4.0 comment。结论：实际RXDR读取宽度、capture地址步进和dump导出循环均未发现“每8字只写前2字”的错误。此结论不排除FIFO硬件通道/字槽语义、现场寄存器状态或实际页表与预期不一致；逐次FIFO trace仍有必要。

来源锁定：当前冻结pio.c/h、k7sound_main.c、i2c_owner.inc、boot.c和chip.h逐项匹配该build verification里的源码哈希，见source-binding.json。早期candidate-review可能是较早候选，本文以实际构建记录/ELF为准。主会话提供evidence/audio-rx-machine-reference-20260910/objdump.txt和result.json，已原样冻结；后者确认原ELF及反汇编哈希。独立核对3328条AArch64指令word全部与本地ELF对应字节一致，见disassembly-check.json。该片段头明确elf64-littleaarch64，没有使用MinGW x86反汇编。

## 实际指令

完整片段reference-objdump.txt，聚焦片段verified-fragments.txt：

* sai_read 0x404bfc60先验证offset<=0x70及4字节对齐；0x404bfc80加载基址0x2a610000；**0x404bfc84 `b8606820 ldr w0,[x1,x0]`**，单次32位MMIO load；**0x404bfc88 `b9000040 str w0,[x2]`**，单次32位存调用者缓冲。没有LDR X、LDP/Q批量读FIFO或省略volatile读。
* PIO rd 0x404c2368装载port.ctx/read函数指针并BLR，返回错误转-5；没有缓存RXDR结果代替第二次访问。
* run RX分支0x404c2b3c `ubfiz x2,x1,#3,#31`得到frame*8，0x404c2b44加capture基址x26；0x404c2b48传offset0x34，0x404c2b4c调用rd。
* 第二字0x404c2b54重新取frames，0x404c2b60左移1、0x404c2b64加1，0x404c2b68 `add x2,x26,x2,lsl #2`得到capture+4*(2*frames+1)；再次offset0x34调用rd。两次成功后0x404c2afc..2b04才frames++。48000帧范围内shift截断不发生；逐帧写地址为base+0/+4、+8/+12……无32字节跳步。
* dump以0x40a1e03c为基址；0x404c037c加word_index*4。外层0x404c0384令行终点index+8，仅用于每行8个数。内层**0x404c03b0 `ldr w1,[x20],#4`**、0x404c03b8字索引+1，逐字printf，直到该行终点或2*captured_frames。不存在跳过后6个字、每行仅读两字或将未读字打印成0的分支。

MMIO与内存路径之间只有CPU的32位load/store，没有DMA填充capture。此路径不需要靠DMA cache invalidation把RXDR搬进数组。函数返回后同一共享缓冲由CPU逐字导出；不能用“未flush DMA缓存”解释这里的规律零洞。

## 地址与映射

实际ELF capture symbol=0x40a1e03c，size0x5dc00=384000=96000*4，区间[0x40a1e03c,0x40a7bc3c)，.bss NOBITS，4字节对齐。96000字足够48000帧双通道；每32位访问自然对齐。非cacheline对齐本身不导致CPU普通读写丢掉固定6字。

elf_audit.py直接解析ELF实际g_mmu_regions（0x4052ac10、16*40字节），不是仅抄源码：DEVICE_REGION VA=PA=0x2a000000、size0x02000000、raw_attrs0x8，包含SAI RXDR0x2a610034；DRAM0_S0 VA=PA=0x40400000、size0x07e00000、raw_attrs0xc，包含整个capture。与同构建boot源码中MT_DEVICE_NGNRNE|RW|SECURE和MT_NORMAL|RW|SECURE对应。表内其他区域未覆盖capture；模型池从0x60000000开始，与capture无交叠。

这证明镜像静态映射表和地址选择正常，**没有读取实板TTBR/页表或缓存配置寄存器**，因此不声称已经验证运行中每一级PTE/MAIR。也未审计全系统所有越界写或多核缓存一致性故障；当前证据不支持它们是已确定原因。

## 工具与可复现性

本机readelf为D:/software/mingw64/mingw64/bin/readelf.exe，SHA256 177a2c6204f8e130591b78645754fb253dd103f25f5215a459d8b28ce8cd0ded，只用于架构无关ELF读取。commands.json记录参数/退出码，header/sections/symbols/segments.txt保留输出；elf_audit.py可本地Python重跑。Windows未找到ARM64 objdump，所以实际AArch64反汇编由root的获授权采集提供；其result.json未记录工具版本/完整命令，本文不捏造这些元数据。逐指令字节比对弥补输入是否对应的问题，但不是工具版本证明。

未操作设备/SDK、未修改正式源码。没有建议修改访问宽度、扩大缓存刷新或按每8字重排样本；先保留当前真实数据和C的逐次FIFO trace，避免把硬件FIFO语义误当普通内存布局错误。

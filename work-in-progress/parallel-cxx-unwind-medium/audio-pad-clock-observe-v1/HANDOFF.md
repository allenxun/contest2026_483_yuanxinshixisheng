# Pad clock observation / SDI0 pull-none candidate

当前GPIO4B3 pull raw0x5555、field1是**下拉**。RK3576_PIN_BANK将各组设PULL_TYPE_IO_1，头文件定义其索引1；rockchip_pull_list[1]={disabled,pulldown,disabled,pullup}。不能沿用另一种IO表将1称上拉。Schmitt rawff表示bit3已开；GPIO EXT bit11采样全0既可能真实输出0，也可能三态受下拉或采样路径问题，不能单独确定原因。

pull-none.patch基于本目录冻结当前正式platform.c/h，仅增加第10个保存字段IOC0x26046144 mask0xc0 value0（HIWORD写0x00c00000）。setup与cleanup已有循环同时扩展10，含读回；恢复按原值只恢复mask0xc0，邻pin不变。不碰drive、Schmitt或其它pin。下一镜像保持baseline codec power/route不变，以识别pull差异；pull-none匹配官方DTS，并非保证消除全零。精确来源见上一独立audio-mic-input-review-v1及本目录新增输入哈希。

observe.c/h不操作mux/DDR/clock，root提供GPIO4 EXT只读回调和已验证CNTVCT原始ticks/CNTFRQ。固定20ms、最多1000000次，统计A2/MCLK bit2、A3/BCLK bit3、A5/LRCK bit5、B3/SDI0 bit11高次数和翻转数、first/last raw、elapsed和最大采样间隔ticks。时钟倒退或冻结次数到顶返回失败，不把未满20ms称完整窗口。root在CLK/FS已开且codec已arm后、RX/TX数据流启动前调用（20ms可包含在现有100ms clocks_started预算中，勿放已启动且无DMA的3秒实时捕获循环导致溢出），退出后再统一打印。root应确认其callback总体时限足够包括codec的30ms延迟和I2C。

读取始终保持SAI mux。GPIO4 PCLK/root/版本/输入采样通路仍是前提；EXT是GPIO驱动外部输入寄存器但源码不能保证每种复用输出都能从EXT读回。因此观察到翻转支持该采样点存在变化；观察不到翻转不能证明时钟未输出（可能复用输入不可见、过快时钟混叠、采样间隔锁相）。20ms软件采样尤其不能精确量4.096MHz MCLK或1.024MHz BCLK，不从changes/2/window自动给实测Hz。LRCK16kHz半周期31.25us较慢，若实际采样最大间隔远小于半周期、正负样本及各窗口结果稳定，可给粗估；仍注明GPIO输入路径/采样延迟和丢边沿假设，不称示波器测量。上下限计数和原始时间全部保留。

样本外部时钟翻转不证明幅度、电压/驱动能力或codec端收到信号；这次可以区分更多假设，无需先要求用户购买工具。全零MIC应与B的codec输出状态对照，不能把有BCLK/LRCK直接宣告录音验收。

test.c验证20ms完整窗口、冻结时钟计数上限、倒退、零frequency；test_platform.c编译真实candidate platform函数，验证0x5555→0x5515、恢复0x5555及非quiescent拒绝。O0/O2原始结果run-evidence.json。未修改正式源码/设备/SDK；root负责接入与真实验证。

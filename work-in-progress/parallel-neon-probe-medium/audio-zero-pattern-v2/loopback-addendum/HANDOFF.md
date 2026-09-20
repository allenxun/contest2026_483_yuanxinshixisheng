# 内部 loopback 独立附录

不改父目录已封存清单。本附录沿用 ../inputs.json 固定的 TRM/官方驱动/PIO 输入，增加纯 C 配置候选与实际 O0/O2 测试。不是完整 duplex PIO 实现，未目标编译、未实测。

**有据路由**：TRM SAI-layout.txt page934 PATH_SEL[23:22]选择SDI0的SDO来源，0=SDO0；bit18开启内部Tx_sdo→Rx_sdi0，bits19..21另三路保持关闭。Linux rockchip_sai.c 1306–1313 的 lp0_enum/lp0_switch 及1682/1686 mixer提供相同映射。SDO0取TX path0、RX path0取SDI0分别为[1:0]=0、[9:8]=0。默认e4e4得到4e4e4。不要动版本更新才有的 LOOPBACK_LR；也不要把Linux rockchip,digital-loopback 的DMA软件注册当成此寄存器使能。

TRM明确要求 fs_tx_as_common、tx=rx=master。本RK3576寄存器映射只有共享CKR/FSCR及XFER时钟/FS控制，CKRbit2=0是master；官方头没有另一个可套用旧I2S_TDM的fs_tx_as_common位。因此助手必须得到调用方common_clock_verified前置确认，并严格检查同一SAI1、TX/RX同一I2S32 profile/shift2、CKR18、FSCR0101f03f。该布尔值是集成契约，不是已完成硬件验证。若无法确认共享时钟，不得为通过测试直接填1。

`lb_plan` 不做MMIO：检查amp低、23073576版本、XFER=0、DMA off、四个IRQ enable off、FIFO空，输出mask/saved/enabled。调用方在平台已上电且独占时读取快照，配置完profile后使用该masked写并读回；起流前检查slot mask仍全0。不要让随后通用初始化覆盖PATH。只改mask=00fc0303，保留其他路由。`lb_restore`仅在调用方确认streams idle且amp低时恢复保存位；恢复读回失败或stop失败保留held，不继续断钟访问。助手的bool不能取代真实状态检查。

**最小有限测试建议**（未实现驱动）：

1. codec保持mute、功放始终低；不调用任何会抬功放的prepare/poststart hook。SAI输出仍可能到codec DAC引脚，但内部loopback不需要ADC参与。
2. TX/RX均同16k/双32slot，分别初始化，启动前16word预填重复8word标记；记录每次TXDR后四银行count，不能假设第0/1word属于bank0。八字由lb_marker生成，全非零且各不相同。
3. 开共享CLK/FS后同时置TXS/RXS（XFER流位2/3）以避免单方向相位偏移；具体应用须沿用现有已核对的CLK/FS启动等待。最多64pair（4ms）或5ms总截止，固定128word接收及前32word trace。继续原TX总count<=14补两word、总入队<=16；每轮处理RX并检查RXOI/TXUI。不要预填仅8字后长期等空，也不要让日志打印打断实时流。
4. 记录RX原字及TX入队序号；允许起始有限对齐未知，但不自动删零/归一化。先全量报告八标记的出现顺序和四相位、FIFO银行序列；有限窗口内无法对齐即未通过。停流沿用已验收时钟保持/clear逻辑，不重复CLKFS关闭时clear。全程amp低，成功停流后恢复PATH并读回。

**能区分什么**：若内部回环仍出现三零相位，codec ADC/外部SDI不再是产生该现象的必要条件；优先查TX/SAI/PIO链。若标记完整按序回收，证明这个内部双向路径能传数据，支持继续查外部输入/路由，但不同启动条件可能改变行为，不能单凭一次通过宣布codec损坏。若只出现标记0/1而其他六个缺失，也可能TX串行化只使用bank0，因此不能单独归罪RX。必须关联实际TX bank落点；两端相同错误互相抵消也可能让loopback通过，不能把loopback当普通录音验收。

模拟测试只覆盖严格profile门禁、masked保存恢复、忙时拒绝、标记唯一/循环，绝不模拟出硬件成功。run.py保留gcc -std=c11 -Wall -Wextra -Werror -O0/-O2原命令和返回值，compile/test原始输出均在本目录。

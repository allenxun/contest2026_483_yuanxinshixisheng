# SAI1 raw32 PIO短探针

`pio.c/h` 可由root统一MMIO端口调用，候选不带板级MMIO地址映射、不操作设备，不改正式代码。使用冻结官方SAI头，GPL-2.0-or-later。源与DTS/CRU/pinctrl逐字输入和哈希在inputs.json。真实Windows GCC O2严格警告编译及寄存器模拟运行通过，原始test-output.txt、outputs.json齐全；没有ARM编译或真机录放音验收。

## 可执行入口

`pio_run(&port, prepared, 4096000, playback, buffer, capacity_words, &result)`：prepared只由root在硬件前提核对后置1。capture使用调用者6400个uint32字（25600字节），成功最多3200帧/200ms，原始FIFO字不改写。playback不需要buffer，生成双声道同值±2^20 signed32、250Hz方波，数字幅度约满幅1/2048（约-66dBFS），最多200ms。不能把低数字幅度视为功放增益/插拔无爆音保证；codec mute与功放门禁由B/root控制。两模式分开运行，不做全双工。建议先功放关闭录音，再独立受控短音；不把录音自动回放。

`pio_summarize`仅对result.frames完整帧计算左右signed32 min/max/sum/nonzero，支持INT32_MIN不溢出，最多3200帧。回传接口是调用者buffer+frames，root可导出原始小端字与统计；不要打印整个buffer到实时轮询中。成功后如要转PCM16，应明确将每字bits31..16按有符号16解释，不使用未定义/实现相关负数右移；是否ADC有效位左对齐和左右顺序仍需B profile及真实数据核对，保留原字以便纠正。

port read/write使用SAI相对offset，root基址0x2a610000。回调返回0才成功，所有回调（包括单调us）必须有界、非阻塞且提供设备MMIO顺序；禁止在回调中printf。只允许单owner，无IRQ handler/DMA/其他SAI用户。预检拒绝已有XFER低4位、DMA request enable、非idle和目标FIFO残留；不会接管活跃SAI。prepared=0/未知版本/非法MCLK返回且不写寄存器。

采样循环250ms墙钟截止，并有100000次上限，clock倒退拒绝；停止最多2000us并每阶段10000次上限。不宣称操作系统抢占或阻塞MMIO回调下有硬实时保证。sample上限独立于clock正确性。RX中途第二word错误不增加完整frame计数，调用者仅消费frames*2字。失败也执行停止；stop_result失败则held=1，禁止调用者自动重试、复位、关外部时钟或假称清理完成。

## FIFO与格式依据

官方rockchip_sai.c:1811 get_fifo_count读取TXFIFOLR/RXFIFOLR，将4个lane的6bit计数相加；本候选只启用lane0并拒绝其他lane计数，RX count>=2才连续读两个word，TX空才连续写两个word。深度不从6bit计数猜为63：官方单FIFO maxburst8及TX threshold16/RX threshold16（:1191–1215）支持至少容纳两个word的推导，但源码未给显式深度定义。本策略不依赖精确深度，只使用空FIFO的两个槽位；真机仍需确认无xrun。

原S16内存打包没有足够明确的PIO依据，故本轮改VDW32/SBW32/两slot/单lane。官方hw_params明确支持S32_LE且DMA bus4，结合每sample4字节提供raw32依据；不复用S16 packed假设。默认SJM_R、MSB、VDJ_L、I2S一bit延迟、RX/TX_SHIFT_RIGHT(2)、FS双边沿，FW64/FPW32；slot mask未改，root须确认初始化/复位后的slot使能状态。path lane0选data0。新SAI offsets和旧I2S_TDM不同，不能替换头。

PIO TX只保留一帧余量，普通调度迟延可能欠载，尤其无线负载下；这是短期可检验探针，不是连续音频方案。INTSR TXUI/RXOI出现即报-75；没有位出现不能单独证明音频完整，状态位在禁IRQ情况下的锁存行为还需实际核验。TX完成等待FIFO空再stop，末尾是否发生短暂underflow也如实报告，不掩盖。捕获开头/结束帧和实际声道需真机样本判断。若PIO在正常运行中持续xrun，下一步使用dmac0请求RX3/TX2，4byte bus、maxburst8、固定双缓冲；必须补DMAC0终止/IRQ/cache所有权，不退回“停止请求即成功”。

## 时钟、pinmux与板级前提

16k*2*32=1.024MHz BCLK。MCLK4.096MHz/4，SAI_CKR_MDIV编码(4-1)<<3=24；12.288MHz/div12也算术成立但不能替代B已选codec MCLK/fs。root转达B raw32 ADC寄存器0x0c=0x10、DAC0x17=0x20，此候选不写codec，只要求该profile核定完毕。

冻结clk-rk3576.c:458：audio_frac0 source CLKSEL13[1:0]；gpll/cpll/aupll/24m parent表index3为24MHz。source fractional在CLKSEL12，gate1 bit10。24,000,000*64/375=4,096,000精确成立。若分数布局经root查实现确认为numerator[31:16]/denominator[15:0]，完整值应0x00400177（64=0x40，375=0x177）；本输入clk-rk3576.c只用COMPOSITE_FRAC宏，不自行证明位布局，也不能用普通hiword-mask写法写该完整分数寄存器。

SAI1 source :1416 CLKSEL46 mux[10:8]=1选择audio_frac0，divider[7:0]目标除1（实际编码由root clk框架核实）；source gate8 bit4、最终MCLK mux46 bit11选内部source/gate8 bit5、HCLK gate8 bit6；MCLKOUT另有gate，不能只开内部MCLK便声称codec已收到时钟。PD_AUDIO10、reset M/H133/134为框架ID，不是原始bit。外部H/M clocks、复位、power domain、分数父时钟共享用户由root先核对，本函数不会盲目重置共享资源。

rk3576-pinctrl.dtsi:3255起：LRCK GPIO4_A5 mux1、MCLK GPIO4_A2 mux1、SCLK GPIO4_A3 mux1、SDI0 GPIO4_B3 mux1；播放SDO0 GPIO4_A7 mux1来自同组。DTS可证明pin功能选择，不等于本函数已写IOC或pad电压正确。MIC按用户已确认连接，不再要求照片。codec I2C3、ES8388供电与slave配置由A/B/root负责。

## 启停与版本

只接受实际VERSION=0x23073576（RK3576源头SAI_VER_2307），不把>=比较扩成任意未知硬件。该版STATUS RX_IDLE bit3/TX_IDLE bit2/FS_IDLE bit1。>=2311位会变化，所以拒绝。配置→TX预填一帧（如播放）→使能CLK/FSS→使能目标stream。停止清stream→对应idle→CLR对应FIFO并等待自清→清CLK/FSS→FS idle；不照搬Linux clear超时reset后返回0的行为。外部MCLK保持，root后续若关它，按Linux runtime_suspend要求在FS idle后至少2个BCLK周期再gate。

模拟测试覆盖成功capture/tone、32bit寄存器数值、前提不满足零写、未知version、非法clock、短buffer、残留活动、采样超时、xrun、停止超时held、MMIO失败held、raw统计边界。模拟FIFO/clock/status不是实板，未模拟codec模拟通路、实际速率、左右声道、FIFO深度或波形。首个真机结论应以root的寄存器读回、实际原始采样和声学确认命名，不能称完整音频已验收。

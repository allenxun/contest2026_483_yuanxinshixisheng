# I2C3 live polling candidate

集成 live.c/live.h + i2c3_timing.c/h，零初始化 struct i3_live，root 提供 read/write/us/lock/unlock/lines 回调。i3_init(...,true) 不访问寄存器；true 表示 root 已核实 I2C3 24MHz 源、PCLK/父链、reset释放、M0 mux、电源/电平、GPIO输入路径、共享owner、GIC排除和接受标准模式默认工程边界。i3_timing 后 i3_xfer 可真实执行，不受simulation-only门禁；未知条件应传false而非伪造准备完成。

本次精确blob已核验Git对象SHA1且保存SHA256：i2c-core-base.c:1810–1820 标准模式默认rise1000ns/fall300ns（property可覆盖）；它们是工程保守边界，不是测量。采用已确认设计xin24m=24MHz，100kHz算出CLKDIV=0x000e000e、tuning=0x1200，理论SCL100kHz。timing写CON tuning+CLKDIV并读回；不从父项名猜当前输入频率。与Linux vendor额外SCL_OE_DB硬件超时编程不同，本小组件不碰该扩展寄存器，采用有界软件超时和STOP证据；挂线/SLV_HDSCL可能需外部恢复，不自动reset。

调用：i3_init(&bus,&port,prepared)，i3_timing(&bus)，uint8_t v; i3_xfer(&bus,true,reg,&v,100000)。写用false并在v放待写字节；地址固定7-bit0x10，一次一个8-bit寄存器/数据。仅在读取及STOP/linehigh全部成功时改调用者输出。写失败可能已产生设备副作用，不保证原子性、不自动重试。root先双次读0/1/2；原值写回必须选codec计划确认普通RW寄存器，不能认定reset/自清/读写不同语义寄存器的“原值”写回可逆。

## 精确顺序和中断

冻结vendor i2c-rk3x.c:352–395 实际没有等待START IRQ的STATE_START：TX先IEN=MBTF|NAK并填TXBUFFER，再CON.EN/START/ACTACK，再MTXCNT；RX先MRXADDR/MRXRADDR、IEN=MBRF|NAK、CON.START，prepare_read设LASTACK后MRXCNT。live遵循该顺序，不加入会卡死的START等待。完成按MBTF/MBRF，NAK优先于完成；RX清MBRF和伴随START。STOP清旧STOP pending、IEN=STOP、CON设STOP清START，轮询新STOP后清pending、IEN=0、CON保留tuning并禁用，再确认线high。

I2C3官方DTS GIC_SPI91=>GIC INTID123；不是SAI SPI188。组件设置IEN但由CPU轮询IPD，因此root必须整个组件生命周期屏蔽该实例GIC IRQ，并确认无另一个ISR/polling owner；回调MMIO须Device映射/屏障，不可被编译器合并。不要全局关闭中断，也不碰别的设备IRQ。read/write回调是同步不阻塞，不能吞掉MMIO fault并回假值。

开头拒绝CON.EN/START/STOP或IEN非零、线不高、锁失败。每次传输循环最多200000次，时间上限由1..100000us参数决定；时钟倒退-EIO，冻结时钟也由次数界退出。失败仍有独立10000us、200000次界限的STOP清理，不能因事务deadline已到跳过STOP。STOP未确认则保留active/held并poison；线低则保持held和poison。监督方可同owner调用i3_cleanup再次STOP/线确认；成功释放锁但poison不清。需要root重新建立完整生命周期才能重试，不通过重调init绕过poison。没做自动复位/时钟关断/强杀DMA；该控制器流程无DMA。

## GPIO4线状态

官方gpio-rockchip.c:53–68 v2 EXT_PORT=0x70、VERSION_ID=0x78；:631起接受01000c2b/0101157c/010219c8；:190起gpio_get直接readl EXT_PORT取pin位。DTS GPIO4 base0x2ae40000，因此VERSION0x2ae40078、EXT_PORT0x2ae40070，GPIO4_B4=SDA bit12、B5=SCL bit13，mask0x3000。i3_gpio_lines(version,ext)是纯解码，不识别版本返回-ENODEV（不沿Linux未知版本fallback v1猜读地址）。

root先核实GPIO4映射、PCLK_GPIO4 gate18 bit5 (CRU0x27200848)、其pclk_bus_root/父gate、电源和输入采样通路已开启；不能读DATA输出锁存代替外部输入，不能为采样擅改DDR/DR/pinmux。DBCLK_GPIO4 gate18bit6是去抖时钟，不能仅凭该门关闭就说原始EXT_PORT不可用；实际input enable/schmitt/复用状态必须由root按板设置确认。EXT_PORT来源证明其是外部输入路径，但源码不证明当前mux11下输入缓冲/供电已生效。建议lines回调读取version一次验证并在受同一owner保护下短间隔采样EXT_PORT；两线持续高至少Standard-mode tBUF=4.7us后才报1，任何低报0，无法确认输入路径报负错误。禁止硬编码lines=1；也不要求新增外部仪器才能实现该GPIO回调。

## 恢复与边界

组件会写CON、CLKDIV、MRXADDR、MRXRADDR、MTXCNT/MRXCNT、IEN、IPD、TXBUFFER和version>=5时CON1=0禁autostop；只读RXBUFFER。root在准备期间保存必要配置（尤其CLKDIV/CON tuning/CON1），事务结束且IEN0/EN0/STOP及线空闲有证据后，才恢复配置/系统gate/mux。IPD是W1C事件，FIFO/计数并非可按旧快照盲目回写的配置。恢复出错保留owner交监督，不把原寄存器快照回写到活控制器。

原始host C mock覆盖TX/RX/NAK、data timeout后STOP、STOP timeout保留owner和后续cleanup、冻结时钟有界、busy拒绝、lines拒绝、GPIO版本解码；检查CNT写前已有START及正确IEN，模拟真实W1C。O0/O2严格C11结果见run-evidence.json。这不是总线电气、真实codec、GIC屏蔽或实板录放音验收。没有设备/SDK/正式源码操作。verify.py可复现，仅本目录输出；inputs.json/blob-inputs.json和delivery.json固定来源与结果。

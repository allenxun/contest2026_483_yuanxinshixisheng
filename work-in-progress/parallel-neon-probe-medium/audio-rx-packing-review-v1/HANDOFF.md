# 真实RX dump周期异常审查

只读两份实际串口dump（文件虽.bin，内容为ASCII hex），未改样本、未输出修复WAV、未访问设备。analyze.py严格验证唯一SOUND_PCM头/END、每行hex下标连续、每行1..8word、总字数=frames*2；两份通过，排除本次文本解析跳行/重复行。原始证据复制input，SHA256见inputs.json；源码与对应capture日志另列source-inputs.json。

## 已确认样本结构

| 证据 | 声称帧数 | 每声道非零 | 非零所在帧索引 |
|---|---:|---:|---|
| 192042（短录） | 3200 | 800 | 0,4,8,...,3196 |
| 192144（长录） | 48000 | 12000 | 0,4,8,...,47996 |

两声道均严格每4frame只有phase0非零，phase1/2/3从头到尾全部0，没有例外。不是前75%零后25%录音。每个8word组表现为L,R,0,0,0,0,0,0。两份phase0都先有连续720个0xffffffff/声道，之后才有变化的数据；剩余非sentinel phase0字的低8bit全部0，符合24bit左对齐形态，但此形态不独立证明正确PCM。左右后续值不同，不是简单整段复制。完整分布、唯一值数、首尾非零索引和间距见results.json，简短真实运行输出analysis-output.txt。

0xffffffff在signed32中是-1（接近静音），不是满幅幅值；它仍不是此处已证明的有效ADC读值，不能自动把它当正常启动静音丢弃。不能通过删除phase1..3后仍标16k来宣称修好：真实frame时间、FIFO有效读序、开始720样本对应的时段尚未确认，去零会改变时间解释。当前3200/48000“frames”只证明CPU写了对应对数，不能作为已验收的200ms/3秒有效录音。

## 正式与官方路径

正式pio每次sum4 FIFO>=2连续两次read RXDR0x34，写capture[2*f]与[2*f+1]，之后f++。底层sai_read→abs_read→rd，最终`*(volatile uint32_t *)address`，没有源码层uint64/8bit读错宽度；dump也按uint32逐字打印，没有四倍步长。未检查目标机器码，因此不把源码检查扩大成总线事务验收。

官方rockchip_sai.c capture DMA addr=base+RXDR、bus width4 bytes、maxburst8；get_fifo_count无条件sum四字段。hw_params32bit/2channels自动lanes=1，VDW32/CSR(1)/SNB2，RXCR00400fff与该路径一致。未找到头文件里独立“CPU FIFO访问宽度/轮转”开关，也未找到Linux PIO读取实现可直接借鉴。DMA burst8与当前异常8word周期有关联的可能性，但仅凭关联不能判定需要跳读6个字或启用DMA就解决。

四个FIFO字段不应直接等同四条SDI线；先前总和算法来自官方，不表示所有直接PIO读必定对应有效slot。这次数据是尚需核定PIO有效读语义的实证。若逐次读正在从无数据bank返回0，必须有完整FIFO before/after及时间佐证，而不是用值是否零来判断读是否有效（真实PCM可以为零）。

MONO_CR RX_MONO bit1、slot选择bits8:2在头中有定义；当前PIO不写它，Linux标准hw_params也不主动写。需要真实MONO_CR读回排除旧状态，但不能将mono切换当四倍packing修复。CSR1/SNB2和PATH e4e4目前没有发现与官方不同的数值；不能盲设CSR4，后者按官方语义会引入更多serial lanes。

## 最小下一采集建议（由root执行）

在独立短capture中固定保存前32次RXDR访问的`time_us、RXFIFOLR_before完整raw、RXDR word、RXFIFOLR_after完整raw`，不得边实时取样边串口打印。连同开始时RXCR、TXCR、MONO_CR、RX_SHIFT、PATH_SEL、DMACR/XFER和实际capture开始/结束us，退出并确认stop后统一导出。重点看每次RXDR是否消耗哪个计数字段、零字时计数是否下降，以及收集48000对实际用了多少时间。PIO时序与总线行为需进一步说明时，再取厂商TRM的RXDR/FIFO PIO访问章节或正式DMAengine路径精确源码，不能凭现有头猜新地址。

该方案仅提证据需求，不在本目录改驱动或访问板子；不触A/B正在做的codec/mux改动。MCLK修复后首次出现变化数据是有效进展，但当前周期异常和启动sentinel未闭环，ASR输入、原样回放和时长验收应保持未通过。

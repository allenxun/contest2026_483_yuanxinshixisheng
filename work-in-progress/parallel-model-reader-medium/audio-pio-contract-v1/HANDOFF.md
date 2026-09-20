# SAI PIO / DMA 一页契约审查

**结论：归档TRM和Linux SAI驱动没有明确规定“CPU逐32位访问非法”“必须burst读取”或CPU访问怎样选择FIFO bank。Linux确实采用固定数据寄存器地址、4字节宽度、按声道数配置maxburst的DMA路径；这不能证明逐字PIO与其等价，也不能把DMA参数反推为PIO硬件限制。** 不作硅bug结论，不建议猜寄存器或展开DMA移植。

原始路径/哈希见 inputs.json；以下行号对应本目录原样快照。

| 事实 | 精确依据 |
|---|---|
| TRM把系统接口定义为AHB slave，含中断与DMA握手。不要把本章接口泛称为已证明的APB FIFO选择协议。 | input/00-SAI-layout.txt:73–75 |
| TXDR偏移0x30、RXDR偏移0x34，字段均31:0；详细表只说写TXDR将数据放进FIFO，读RXDR访问接收FIFO。概览把RXDR属性写W，而详细字段是RW/明确read，存在文本属性矛盾，不能据概览说RX不可读。 | 同文件:309–310、759–771 |
| FIFO0..3各有独立level字段；驱动get_fifo_count将4项求和。计数求和不是CPU bank映射文档，也不是启用4条lane。 | 同文件:628–654；input/02-rockchip_sai.c:1813–1829 |
| DMACR.RDE/TDE为DMA请求使能；RX水位为RDL+1。TX请求文字明确按CSR选择FIFO0/1/2/3与TDL比较；该句限定请求触发，不能移用为RXDR/TXDR的CPU寻址选择规则。RX请求段没有相同bank说明。 | input/00-SAI-layout.txt:665–690 |
| Linux MAXBURST_PER_FIFO=8；probe将TX/RX DMA地址分别设base+TXDR/RXDR，addr_width=DMA_SLAVE_BUSWIDTH_4_BYTES，初值maxburst=8。hw_params覆盖maxburst=8×PCM_channels/2，所以2声道8、4声道16。它是配置的maxburst参数，不是实测每次AHB事务的burst长度或最低合法访问量。 | input/02-rockchip_sai.c:33、549–550、1191–1209 |
| Linux设置TDL(16)、RDL(16)；宏RDL(x)=(x−1)<<16，因此实际RX字段15、水位16，不能误写字段16当水位16。该水位与maxburst8不同，也不能用水位定义帧数。 | 同文件:1212–1215；input/03-rockchip_sai.h:112、117 |
| stream启动/停止调用dma_ctrl，使能/关闭RDE/TDE；正常注册dmaengine PCM，digital-loopback注册DMA DLP。no-dmaengine分支标注用于Multi-DAI并返回，不是一个PIO实现。该C文件没有CPU持续读RXDR/写TXDR的音频循环。 | input/02-rockchip_sai.c:291–308、398–404、1968–1977；TXDR/RXDR其余引用仅regmap分类 |
| 正式PIO逐次读RXDR，将两次读取记作软件一帧，以四level之和判断可读；该策略尚缺所需CPU bank/相位契约。 | input/04-pio.c:8–16、40–49、183–199 |

**当前现象与未知：** 主会话报告CSR一lane每四pair仅一pair有效、两lane数据/零pair交替。这是待解释观测，本次未采集或重算。它与lane数量有关的变化值得保留，但现有资料无法区分CPU事务属性、银行轮转、启动相位、缓存/MMU映射、串行lane路由等原因。不能把规律本身当作FIFO规范，不能直接声明剩余零是可删除padding。

**可执行的证据边界：** 保留当前格式/寄存器/完整编号raw及时间；由主会话当前独立实验核对实际MMIO映射与已知图样的读取顺序。若将来比较真实DMA，必须记录实际控制器配置和相同格式下的数据/时序；本报告不授权启动DMA，也不建议只开RDE来模拟DMA。找到明确硬件文档或可重复的固定(lane,slot)→读取序号证据后才设计解复用，不能按数值删零或混合反相声道。

交付为只读资料审查，无代码补丁、无硬件测试、无SDK运行或下载。未声称资料缺失代表硬件不支持PIO。

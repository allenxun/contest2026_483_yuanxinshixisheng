# 真实trace结论与单变量复位隔离候选

新独立目录，旧交付及清单不动。冻结真实194104 capture bin/json、官方SAI源码、TRM与当前PIO；输入SHA见inputs.json。无设备/SDK/正式源码写入。

## 实机证据改写了哪项判断

trace start374886177/end375086217，差200040us，CPU3200对与16kHz时间一致。FIFO按0/1/2/3循环，每组读前2/1、读后1/0；零字也消费真实bank有效entry。因此不是CPU空读返回0后无依据增长frames，也不是串口四倍扩展；是串行时间推进时不同FIFO收到相应字，bank0含输入而其他bank为0。MONO0/RX_SHIFT2/RXCR00400fff/PATH e4e4排除了先前已提出的mono、额外loopback或错误SDI0route简单差异。

这仍不能凭结果直接断言硬件缺陷、CSR必须改4或需要去零。官方get_fifo_count求和是正确的统计操作，但不解释为何CSR00下按实际frame时间轮转到4bank。TRM TX TDL依CSR选水位，未明确PIO数据分配的CSR生效条件。官方Linux始终DMA路径，而当前RDE/TDE=0，是值得独立对照的模式差异；尚无证据证明CSR只在DMA模式有效。

当前可定位的官方初始化差异：Linux init_dai设置TDL16/RDL16（DMACR阈值部分0x000f0010），PIO阈值0；Linux START设置RDE或TDE，PIO明确关闭；Linux probe取得reset句柄但不主动pulse，reset仅clear超时恢复。三项不能混为一条“已知根因”。本候选仅复位实验，不改DMACR/CSR/数据过滤。

## reset_probe.c/h最小行为

sr_once(port,result,root_exclusive)只执行一次H+/H-/M+/M-，每条边沿get_reset读回确认并等待10us，顺序来自官方rockchip_sai_reset。result须首次零初始化，attempted防重复；root_exclusive为可信的rails/MMU/HCLK/MCLK可用、codec muted/ampoff、无DMA/IRQ/worker、reset mapping已核实的证明。

预检reset两线均释放、VERSION23073576、DMA请求位均0、XFER低4bit0、STATUS全idle及两FIFO无残留。预检失败不做reset。不会在任何reset线assert期间读SAI。每个10us等待额外10000次上限，clock停顿/回退返回错误，所有callbacks须非阻塞有界。set_reset/get_reset由root提供真实H/M线映射（不能将DT框架ID直接当CRU bit），候选不写未经独立证实的绝对复位地址。

保存before/after五寄存器：VERSION/TXCR/RXCR/PATH_SEL/DMACR。发生任一步reset/读回/计时错误保持held=1，不自动清线后假成功，交给root监督。成功仅completed=1且held=0表示复位序列结束；needs_reapply始终1，音频仍未ready。root必须重设完整SAI profile并读回（包括格式、shift、path/mono/slot已核定初态、DMACR请求关闭与原阈值），然后原样重复trace。不能复位后沿用旧的软件“已配置”标志。

推荐受控顺序为：正常platform setup完成且codec尚未arm、ampoff → 记录前状态 → sr_once → 重新应用原SAI profile → 仍DMACR0的同样capture/32-read trace。也可在已证明停止/ampoff后进入单独实验，但不得把它设成每次失败自动reset。对照仅改变reset是否执行，其他参数/采集处理保持一致。若4bank轮转保留，再安排独立DMA-request模式实验，先确认DMAC0所有channel无残留/其他owner；设置RDE不等于许可任何DMA channel随意搬运，本交付不设置该位。

## 主机测试与边界

run.py真实MinGW GCC O0/O2 C11严格警告编译运行通过，test-output.txt原始命令/输出/exit。模拟验证严格H+/H-/M+/M-顺序、每edge等待、活动状态拒绝、复位期间无SAI读、set失败held、计时停顿有限结束、必须needs_reapply。不模拟bank分配，所以不能用这些通过宣称已修录音。完整源/测试/清单最终SHA见outputs.json；后续补充另建目录或addendum清单，不覆盖本次已引用文件。

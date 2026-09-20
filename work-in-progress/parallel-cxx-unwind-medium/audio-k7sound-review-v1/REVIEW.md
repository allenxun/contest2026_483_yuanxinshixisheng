# k7sound integration review

只读inputs.json对应快照，无构建/设备操作。I2C已有audio-io-b真机通过不代替新SAI/codec录放音验收。未发现SAI偏移白名单与本次frozen header不匹配：读到VERSION0x70、写到RX_SHIFT0x68都允许。codec毫秒deadline与PIO/平台微秒callback的单位接线正确；SPI188=>220和I2C SPI91=>123一致。GPIO2_B1低先行、v2 DR/DDR低半写法、GPIO reset bits1/2和SAI reset bits5/6与冻结定义一致。

## 建议先核实/修正的时间基准

pio.c对streams_started和amp_off_fast要求耗时<100us，stop也设1000/2000us边界。i2c_owner.inc now_us实际来自CLOCK_MONOTONIC，乘换单位不能增加分辨率。已冻结audio-io-b配置为USEC_PER_TICK=1000、SCHED_TICKLESS=n、CLOCK_TIMEKEEPING=n；本地尚无精确NuttX clock_gettime实现，不能直接断言它必定只有tick分辨率，但这是具体集成风险。若该路径按tick返回，一个几微秒GPIO callback跨tick可显示1000us，使成功的amp操作被判-ETIMEDOUT，pio held保留、kd_stop因data_held拒绝，最终无法正常清理。请root核实本镜像实现/clock_getres，或将PIO/平台us回调换成已验证的ARM64单调硬件counter换算；codec ms可继续用一致可靠时间基准。不要用误差很大的时基评判100us回调。

## 真实错误清理缺口

k7sound_main.c末尾恢复old_audio_root/old_audio_gate的两次masked写没有读回、错误变量；即使HCLK_ROOT source/gate恢复失败也可能总体return0。此前I2C恢复已做读回，这段新共享音频HCLK恢复应同样比较mask3和mask2，把失败纳入最终返回与故障锁存，不能只让platform_rc代表另外9个platform字段的恢复。无需扩展权限框架，只补该实际恢复字段的验收。

## 有条件的PIO尾部竞态，非已观察故障

TX最后一帧已入FIFO后，循环仍先检查TXUI，再检查FIFO空以结束。若最后一字排空到下一次poll之间硬件产生underrun，正常有限样本尾部可能报-EOVERFLOW，尽管全部数据已提交；这不是证明实际必发生。保留中途underrun严格错误，实板若总在frames=请求数且FIFO=0失败，应区分终点停止策略/尾部事件与中途供数不足，不能直接忽略所有TXUI。不要为了绕过而删状态检查。本报告不改C代理PIO候选。

CON1通过i2c_owner.inc保存/恢复并读回，现有缺口已修。bus.active/held或data_held保留时拒绝关钟/恢复是刻意失败关闭，不是自动清理成功。sap_setup中途失败留下platform.held且主命令锁存也符合当前组件合同；报告应显示未恢复，不将它算作已收尾。GPIO lines两次高样本仍只是有限idle判据，不能冒充物理连续电平测量。

没有从源码发现确定会让所有probe/tone/capture必失败的回调单位或寄存器偏移错误。主要优先项为微秒时基核实与HCLK恢复读回；录放音是否工作仍要root真实结果。

## 追加UART6/BT交叉核对

root已明确修正版将改用CNTVCT/CNTFRQ商余换算微秒，解决上面时基疑点；未读取修正版产物，不把本报告旧快照视为新版本验证。UART6正式源GPIO4A4/A6使用IOC4084 mask0x0f0f；SAI GPIO4A5/A7使用同地址mask0xf0f0，掩码不交叠。SAI A2/A3在4080 maskff00、B3在4088 maskf000，与UART6不同。UART6时钟CLKSEL65、gate13bit15/gate15bit2不被SAI frac0/SAI1字段覆盖。skw_bt通过SDIO slot解码路径工作，未见其使用这些SAI pins。PMU动作限定AUDIO域，未见直接关闭SDIO域的动作。当前CRU/IOC局部掩码未发现与UART6/BT必然冲突；保留首次真机共存验收，不把静态不重叠说成实测稳定。剩余建议仅HCLK_ROOT恢复读回；无新增确定阻断，勿因此扩大任务。

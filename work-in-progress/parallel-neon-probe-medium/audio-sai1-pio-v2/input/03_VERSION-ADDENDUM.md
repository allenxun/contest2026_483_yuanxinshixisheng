# 版本与分数时钟补充

root后续已冻结clk.c并确认fractional divider mshift16/mwidth16/nshift0/nwidth16；据此0x00400177就是64/375，24MHz下4.096MHz。这个新增证据在root控制的冻结目录，本子候选未重新读取/复制该文件，因此区分为root提供的已核对事实。

官方rockchip_sai.c的poll_stream_idle:174及poll_clk_idle:152给出以下精确表。pio.c保持只允许2307，避免将未知的其余版本初始化状态一并推定；root至少可以按本表诊断读取的VERSION。

| VERSION常量 | 状态寄存器 | RX idle mask | TX idle mask | FS idle mask |
|---|---|---|---|---|
| SAI_VER_2307=0x23073576 | STATUS0x6c | 0x08 | 0x04 | 0x02 |
| SAI_VER_2311=0x23112118 | STATUS0x6c | 0x04 | 0x02 | 0x01 |
| SAI_VER_2401=0x24013506 | STATUS0x6c | 0x04 | 0x02 | 0x01 |
| SAI_VER_2403=0x24031103 | STATUS0x6c | 0x04 | 0x02 | 0x01 |
| 未知旧版本<2307（仅描述官方算法，不是本候选允许列表） | XFER0x10 | 0x100 | 0x80 | 0x40 |

如root读出2311/2401/2403，最小实现扩展应同时替换启动前全idle mask及stop流/FS mask，且检查XFER.TX_AUTO bit6关闭、frame expansion/chain/loopback为已核定初态；不能只放宽version条件而仍用14/8/4/2。>=2311新增TX_AUTO与FSXN，>=2403新增loopback LR，源头有能力区别，不能仅凭idle表宣称整套配置兼容。

本探针是分开capture与playback，不是同时duplex。两次pio_run不可并发，共用FS/CLK时第二个预检应Busy；如需要全双工，必须在一个owner/一次启停内同时服务两个FIFO，不能启动两个worker各自stop关共享clock。初次建议root顺序采集、统计、短音确认，保留现有单方向测试覆盖。

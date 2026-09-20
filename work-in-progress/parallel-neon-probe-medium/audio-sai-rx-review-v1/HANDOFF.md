# SAI RX路径与官方Linux对比

范围：只读当前app/k7sound pio/platform、冻结官方rockchip_sai.c/h与K7 DTS。输入逐字快照及SHA见inputs.json。没有修改正式代码、SDK、设备或其他候选。root报告实际TX3200帧完成且听到短音；RX3200/48000帧完成但全零。这个报告说明时钟/PIO计数路径可运行，不足以证明ADC数据通路有效。

## 已匹配的配置

| 当前值/操作 | 官方函数依据 | 结论 |
|---|---|---|
| RXCR00400fff（TX也相同） | fmt_create:431 I2S；hw_params:536；set_tdm_slot:994 | VDW32、SBW32、SNB2、CSR1、VDJ_L、EDGE_SHIFT_1、MSB、SJM_R、standalone，匹配32bit stereo单serial lane |
| RX_SHIFT2 | fmt_create的I2S分支给XSHIFT_RIGHT(2)，同时更新TX/RX | 与官方一致，宏注释step0.5cycle，2表示一BCLK，不应改成0试图对齐 |
| FSCR0101f03f | hw_params FPW_HALF_FRAME_WIDTH/fw_ratio1 | frame64BCLK，pulse32，双边沿，匹配两32bit slot |
| CKR18 | set_fmt BP_FP/NB_NF；hw_params MDIV | master、正常极性、MDIV4；4.096MHz/4=1.024MHz，/64=16k |
| PATH_SEL RX bits9:8清0 | path_config RX_PATH(0,0)，rpaths_text[0]="From SDI0" | route0选择SDI0正确；不能通过CSR去选择GPIO输入 |
| 先XFER CLK/FSS，再RXS | prepare:654、trigger:785→start→xfer_start | RX不需要TXS启动；CLK与FS是共用发生器，capture单独使能RXS可行 |
| DMA请求关闭、CPU读RXDR | Linux正常触发会先RDE使能再RXS | PIO有意差异；RDE用于DMA请求，不应为修全零盲开DMA |

freeze.py只验证上述已报告数值的整数解码，输出register-decode.json，不将其称为新的板端读回或测试。

## 精确差异与尚缺读回

1. Linux regcache defaults给PATH_SEL完整0x0000e4e4，运行resume执行regcache_sync。K7板DTS没有sai-rx-route覆盖。PIO只更新bits9:8，因此未建立上层路由默认值。官方mixer字段定义证明：bit16 sync_in=0 From IO/1 From Sync Port；bit17 sync_out=0 From CRU/1 From IO；bits18..21为四组loopback enable（0禁用）；bits22..29选择loopback SDO源。若bit18开启且SDO0静态零，则内部loopback可能屏蔽真实输入，但当前没有PATH全raw，不能认定此为根因。

最小下一项证据就是root计划的PATH_SEL全raw：先看bits9:8=0，再看bits16..21=0。若为默认e4e4或相关位全0，SAI RX route0与Linux一致，不需要额外SYS路由。如果相关位不为0，在独占/已停流后才可按已核定profile清mask0x003f0300（RX0路由及sync/loop enable），目标0；这个是基于已读差异的条件性修正建议，不是本交付执行的补丁。不必改其他lane的identity route，也不必为了录音修改TX path。

2. Linux prepare在DIV配置后先udelay20再开CLK/FSS；PIO没有这段开CLK之前等待（codec hook中的延时在CLK启动之后，顺序不同）。这是可明确补齐的启动整洁性差异；官方理由是一BCLK分频就绪与干净出钟，不是证明持续3秒全零由此造成。root可统一平台时基加20us，避免把它和ADC/route切换混为一个不可归因的改动。

3. 当前PIO未更新MONO_CR。官方标准hw_params/prepare也不主动写mono，但头/mixer有RX_MONO bit1、选slot bits8:2。若存在旧bootloader状态，完整MONO_CR读回可消除这一未知；不能凭未设置就宣称默认开启。RX_SLOT_MASK0..3在官方这里只列为可访问寄存器，set_tdm_slot实际只设SBW，不写slot masks。所以缺slot-mask写入不是本范围内的Linux差异，禁止猜全1/全0值强写。

4. RX_SHIFT目前按mask更新，需一次实际读回值2；RXCR已经给定00400fff就无需重复猜CSR。start期间XFER低4bit对capture应0xb（CLK/FSS/RXS）；stop后自然0，不能用退出后的0认定未启动。观察到连续FIFO数据只证明控制器在收样，不证明SDI引脚/codec输出非零。

5. rockchip_sai.c虽然include linux/mfd/syscon.h，实际没有syscon_regmap_lookup/GRF/syscon写或专用SYS CSR路由调用。此结论仅限冻结官方驱动及给定K7 DTS，不扩展为所有RK3576 SoC功能都无需系统路由。未发现应补的独立SDI0 SYS寄存器依据；GPIO4_B3 mux由A检查，ADC/ASDOUT由B检查。

## 结论与接入边界

本范围内RXCR/格式/分频/RX_SHIFT/SDI0字段没有发现数值错误。最值得补齐的是PATH_SEL上层sync/loopback的完整读回，以及DIV到CLK的20us启动等待；不能因此声称已经找出全零根因。真实SDI输入电平/codec ADC通路未在本任务访问或推断。无需开启TX来“给RX提供时钟”，不要改FIFO聚合、raw32打包或取消错误门禁来消除全零。主会话应以独立配置差异和实际采样证据继续定位。

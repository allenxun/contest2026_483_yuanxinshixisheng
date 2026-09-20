# 平台setup候选（新增platform.c/h）

root请求补齐PMU/clock/pinmux，所有写操作经root提供的绝对地址MMIO port，子任务没有访问设备。新输入精确冻结audio-power-reference中的pm_domains.c、clk.c/h及来源记录，更新inputs/outputs哈希。`run.py`同时运行原PIO测试和新platform模拟测试，C11 O2严格警告通过，原始日志保留。

接口：零初始化sap_state，单owner调用 `sap_setup(port,&state,exclusive)`；成功state.ready=1、held=1，提供version/repair/ack/idle/clk46/fraction只读诊断值。ready仅表示平台配置与读回，不表示codec或PIO已就绪。建议root在调用之后打印一行十六进制快照，禁止在轮询回调内打印。exclusive必须由可信平台证明：audio_frac0、AUDIO domain转换和SAI1选定pins无其他用户；codec mute/amp关、rails/MMU/CRU/IOC可访问；HCLK_AUDIO父源已开、SAI复位已释放。该组件不猜SOFTRST编号映射、不控制GPIO2_B1、不调用codec。

PMU依据pm_domains.c DOMAIN_RK3576 AUDIO: pwr8/repair8/request offset4 req0 idle/ack16 clk-ungate0；rk3576_pmu基偏移210/570/110/128/120/140。setup依次：force-ungate PMU144 bit0→PMU210 bit8清零开电→poll PMU570 bit8置位→PMU114 bit0清零解除idle→poll ACK120/IDLE128 bit16都清零。每poll10ms且100000次上限，所有回调必须非阻塞有界；MMIO barrier由port保证。未满足任何一项，绝不碰SAI页。已有power-on也不会默认有效，而重核repair与idle状态。

clock/pin字段先保存；gate住SAI MCLKOUT、M/H clocks、frac0后重新配置：

| 地址 | mask | value/含义 |
|---|---|---|
| CRU334 | 0x3 | 3，xin24m parent |
| CRU330 | 全32位普通写 | 0x00400177，64/375，4.096MHz |
| CRU3b8 | 0xfff | 0x100，SAI1 source=frac0，div1，最终内部源 |
| CRU804 | bit10 | 0，frac0 gate enable |
| CRU820 | bits4/5/6 | 0，SAI1源/最终M/H clocks enable |
| CRU824 | bit13 | 0，SAI1 MCLKOUT enable |
| IOC4080 | 0xff00 | 0x1100，GPIO4_A2 MCLK / A3 SCLK mux1 |
| IOC4084 | 0xf0f0 | 0x1010，GPIO4_A5 LRCK / A7 SDO0 mux1 |
| IOC4088 | 0xf000 | 0x1000，GPIO4_B3 SDI0 mux1 |

CRU基址27200000，IOC26040000，PMU27380000，SAI2a610000。除分数寄存器外均hiword mask写，逐项masked读回；分数布局由新冻结clk.c确认16:16。pinctrl bank4 offsets和4bit iomux字段推导上述掩码，固定pin组不触碰I2C3 GPIO4_B4/B5。没有改pull/drive/pad电压，root须确认现有板级电气设置适用。

全部成功后清PMU force-ungate位，读回clock配置，再首次读SAI VERSION0x70。不写任何SAI寄存器、不启动流；读到未知version仍返回平台setup成功，后续PIO version门禁单独负责拒绝。这样root能在不开流时获取真实ID以选择已证实profile。

`sap_cleanup(port,&state,quiescent)`仅在setup成功且root确认PIO/DMA/IRQ/worker全部停止、FS idle后至少2 BCLK周期才允许。先gate endpoints/frac0，恢复原source/div/fraction/pins，再恢复原gate字段并读回。AUDIO电源保持开启、NIU保持de-idle；未保存QoS/其他AUDIO用户，因此绝不擅自power-off。setup失败或cleanup失败保留held，调用者不能把错误吞掉或强制撤销；由root监督读可安全的PMU/CRU再决定恢复。无自动重试，attempted保持。

测试模拟hiword mask和完整分数写；验证no permission零写、正常配置/version读、未quiescent拒清理、恢复、禁止重入、power timeout绝不读SAI及held保留。模拟不证明pad/时钟实际波形、power transition、reset或总线可达。正式ARM64构建和preflight由root完成，不能把host通过写作实板音频通过。

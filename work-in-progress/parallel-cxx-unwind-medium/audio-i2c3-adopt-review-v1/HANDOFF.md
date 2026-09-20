# I2C3 preexisting gate-on adoption review

真实 preflight 两份一致：SEL0=cf3、SEL1=147、SEL55=20、SEL57=0、GATE0/11/12=0、IOC408c=0。功能父为clk_gpll_div6，目前其parent GPLL、divider字段5即/6；PCLK父为clk_cpll_div10，其parent CPLL、divider字段19即/20。名字div10不等于当前/10。当前原始值不能证明PLL真实rate。两门打开、pins GPIO不能推断总线占用，也不能直接接管。

主会话先确认当前已加载映射实际含DEVICEIO 0x2a000000+0x02000000（范围覆盖2ac60000），不是仅根据源码声明推断当前页表。检查PCLK_ROOT/选中父gate、PCLK_I2C3 gate、供电与访问权限；读取CRU reset状态0x27200a30掩码0x4004，要求为0（SRST_P_I2C3=194=>12*16+2、SRST_I2C3=206=>12*16+14；SOFTRST_CON偏移0xa00+4*n依主会话已核验宏）。不解除reset，不以读取控制器试探reset/pclk是否可用。

满足访问条件后，在持有所有使用方共同遵守的物理总线/系统字段独占锁下，仅先读I2C3 CON 0x2ac60000与IEN 0x2ac60018。CON.EN bit0、START bit3、STOP bit4任一非零，或IEN非零，均拒绝接管；不要清零它们。需确认没有polling线程/IRQ/延迟回调正在或即将访问。可在锁内再次读确认稳定，但重复相同仍不能替代owner证明。EN=0/IEN=0是必要条件，不是完整idle证明；还需外部线路已释放、pin原owner允许切换、电源电平兼容。CON读数不能代替线电平。

adopt.py为纯计划：仅在原PCLK/功能门均开且上述证据均成立时，暂关功能门（0x27200830写0x40004000）→CLKSEL57选择xin24m（0x00300030）→恢复开功能门（0x40000000）→再次确认控制器不活动/线路可切换的barrier→IOC写0x00ff00bb。全程不改PCLK位、不改PCLK_ROOT/PLL；暂关已确认静止功能门是避免带时钟切父，不是用门控强停活事务。所有写读回匹配后才进入下一步，不能删barrier直接执行写数组。

恢复复用冻结上一版字段历史逻辑，逆序mux恢复→暂关功能门→原source恢复→原功能门打开，恰好保持原先gate-on状态；仅mask恢复，旁邻位不改。支持每个已完成写前缀。恢复前先确认无事务/访问并保持独占，逐字段比较当前值与本计划预期，冲突拒绝盲目回滚，未确认写先读回；失去共同锁或外部未知写者时不保证无ABA/compare-write竞态。原source恢复之前功能门保持关闭。后续timing/CON改写需要独立状态日志，在恢复系统门控前处理，不能由本计划代办。

reset只作读取门禁，不是强制prepare步骤。冻结rk3x源1198起实现reset，1310起仅超时且SLV_HDSCL恢复调用，不支持每次adopt无条件reset。当前未采集reset/CON/IEN/线路读数，不能宣布可执行或audio ready。

时序默认来源边界：冻结i2c-rk3x.c:1580调用i2c_parse_fw_timings(...,true)，请求通用I2C core默认值；本次已有冻结输入未包含该函数实现，因而不能将常见Standard-mode rise=1000ns/fall=300ns归为已核验这版SDK的精确实现。请主会话若采用默认值，补取该实现及实际DTS相关属性。Linux按模式提供的默认时序即使核实，也只是工程保守设计边界，并非板端测量；需显式标明采用的约束及适用性，不能把合成测试100ns冒充板值。DTS xin24m 24MHz可以作为已确认板设计输入，不称物理测量，也不要求用户另购仪器才能写候选；电源/idle/rise/fall未知仍必须如实保留，不自动推进传输。

inputs.json固定实际采集、官方源和候选快照。原始主机结果run-evidence.json；复现python -B test_adopt.py。测试只验证纯计划、前缀恢复和拒绝条件，没有硬件动作。旧交付/正式/SDK/device/logs均未修改。

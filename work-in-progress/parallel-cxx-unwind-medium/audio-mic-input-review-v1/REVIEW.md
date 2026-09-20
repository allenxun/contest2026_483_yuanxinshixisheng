# GPIO4B3 SAI1 SDI0 review

结论：现有IOC26044088 mask0xf000→0x1000正确。未找到该pin另需GRF路由或独立pad input-enable写的官方依据，不能把全零直接定性为漏input-enable。板端tone通过且用户听到、capture返回完整帧但全零是root提供的新事实；本审查没有操作设备，也不重复ADC功耗/codec路由分析。

具体来源：冻结rk3576-pinctrl.dtsi:3276–3281 sai1m0_sdi0=<4 RK_PB3 1 &pcfg_pull_none>；SoC rk3576.dtsi:4454起SAI1默认组包含该输入；K7 dtsi:245起也显式包含sdi0。pinctrl-rockchip.c:5238 bank4 B offset4088，4bit pin11%4=3，得到bits15:12。RK3576特殊mux路径:1293起仅GPIO0B4..7偏移和特定I3C weakpull，不含GPIO4B3；rk3576_pin_ctrl:5241起没有iomux_routes表。源码未出现SAI1输入额外GRF选择。

**不要套通用PIN_CONFIG_INPUT_ENABLE修复。**该驱动:3886起实现先rockchip_set_mux(...RK_FUNC_GPIO)，再gpio.direction_input，会撤销SAI mux。GPIO DDR设输入也不是官方SAI DTS所要求的步骤；不能为了“输入”改GPIO模式而破坏外设采集。

精确官方rockchip-pinconf.dtsi已从对象库读取并核对Git blob OID，:18–20 pcfg_pull_none只有bias-disable，无input-enable或schmitt-enable。当前platform仅mux并未同步pull，这是一项与Linux配置的差异，但下拉是否导致全零要有实际状态/驱动能力证据，不能先假定。Schmitt是单独可配特性，不等于输入缓冲总使能；该SAI pin的官方默认组未要求它。

## 最小只读诊断（由root执行）

| 地址 | 字段 | 解释 |
|---|---|---|
| 0x26044088 | 0xf000 >>12 | SDI0 mux应1 |
| 0x26046144 | 0xc0 >>6 | GPIO4B3 pull；官方bias-disable写值为0，现有IO_1表也允许编码2读成disabled；不要把所有非0都称下拉 |
| 0x26046244 | bit3 | GPIO4B3 Schmitt状态，仅记录，不是已知缺失使能 |
| 0x2ae40070 | bit11 | GPIO4 EXT_PORT实际pad采样；已有v2版本/PCLK访问前提成立才读 |
| 0x2a610038 | bits9:8、bit18、bits23:22 | lane0 RX source应0；SDI0 loopback enable应0；loopback源选择仅在enable时有效 |

pull来源pinctrl.c:2789–2829：bank4低16 pin base6140，pin11/8加4，pin11%8*2=6。Schmitt:2834–2875：base6240+4，bit3。上述均IOC26040000基址派生，未写任何值。

SAI_PATH_SEL来源vendor rockchip_sai.c:710–717 RX路径、:1258 Disable/Enable枚举、:1309/1313 SDI0 loopback源/开关。当前PIO只将bits9:8清0，未清bit18，若前序留下loopback开启可能绕开外部SDI0；**这只是可由一次raw读数判别的假设，不是已证明根因**。vendor默认PATH_SEL=0xe4e4 (:1138)中bit18为0，不应声称默认就有问题。勿根据假设直接写全部PATH_SEL。当前sai_read允许offset<=0x70，0x38在范围内。

在采集运行期间可有界稀疏统计EXT_PORT bit11高/低次数及转变数，循环内不串口打印；不改mux为GPIO、不主动输出、不加入pull扰动。某次高或观察到翻转证明pad并非始终低，但不能恢复完整I2S数据。有限采样始终低可能是codec真正输出0、路径断开、三态/下拉或采样混叠，不能单凭它定性。若GPIO样本翻转而RXDR持续0，优先对照SAI内部PATH/RX格式；若pad一直低则与B的codec输出证据一起区分。保持原始帧数据与诊断时间/固件哈希，避免零填充或声称录音已通过。

建议只加以上raw读数与受限EXT统计；没有足够依据生成“强开输入”补丁。全部输入/精确blob来源哈希见inputs.json、blob-input.json；无SDK构建区、正式文件或设备修改。

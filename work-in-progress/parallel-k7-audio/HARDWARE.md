# K7 音频证据核对

范围是 `K7_V2.0_20250716_SCH.pdf` 与 `K7_V1.1_20241211_SCH.pdf` 的相关完整页面、官方 Linux 本地 Git blob、当前统一项目 overlay 和 model-arena 构建配置。以下页码均为 PDF 从 1 开始的物理页码；图中跨页标签仍出现 [37]/[38] 等旧编号，不能用作 PDF 页号。两份文件的音频标题栏均保留 K7_V1.1，V2.0 文件名并不足以确认用户手上 PCB 板版或实际装料。

| 项目 | 核对结果 | 直接依据 |
|---|---|---|
| codec | U7000 标 ES8388，QFN28；并非仅依赖原 VoiceLink 假设 | 两版 p32 |
| I2C | I2C3 M0，CE pin26 接地，7-bit 0x10；CE 高才为 0x11 | 两版 p32；K7 DTS 206–219 |
| I2C pinmux | SCL GPIO4_B5、SDA GPIO4_B4，mux 11，2.2 kΩ 上拉至 VCCIO_AUDIO（R1800/R1801） | 两版 p16；rk3576-pinctrl.dtsi 1715–1721 |
| 数字音频端口 | SAI1 M0，以 I2S 格式工作；不能误移植旧 SoC I2S TDM 寄存器 | 两版 p16/p32；K7 DTS 46–49、245–251；rk3576.dtsi 4454 起 compatible sai-v1 |
| MCLK | GPIO4_A2 mux1 → U7000 pin1；DTS 初始请求 12.288 MHz，声卡按采样率×256重设 | 两版 p16/p32；pinctrl 3262；K7 DTS 216；rockchip_multicodecs.c 373 |
| BCLK/SCLK | GPIO4_A3 mux1 → U7000 pin5 | 两版 p16/p32；pinctrl 3269 |
| LRCK | GPIO4_A5 mux1 → U7000 pin7 | 两版 p16/p32；pinctrl 3255 |
| 播放数据 | GPIO4_A7/SAI1_SDO0 mux1 → DSDIN pin6 | 两版 p16/p32；pinctrl 3304 |
| 采集数据 | ASDOUT pin8 → GPIO4_B3/SAI1_SDI0 mux1，经 R7001/R1802 0Ω | 两版 p16/p32；pinctrl 3276 |
| SAI clocks/reset/DMA | mclk/hclk 为 MCLK_SAI1_8CH/HCLK_SAI1_8CH；SRST_M_SAI1_8CH/SRST_H_SAI1_8CH；PD_AUDIO；dmac0 tx2/rx3；地址 0x2a610000、IRQ GIC_SPI188 | rk3576.dtsi 4454–4475，仅 Linux 参考，不表示 openvela 已配置 |
| MCLK 输出控制 | mclkout_sai1，CLK_SAI1_MCLKOUT，0x26046400 bit1 的 disable 属性 | rk3576.dtsi 153–162；不得未经 CRU/GRF 审计直接写整个寄存器 |
| codec 电源 | DVDD/PVDD 为 VCCIO_CODEC，来自 VCCIO_AUDIO=VCC_1V8_S0；AVDD/HPVDD 为 VCCA3V3_CODEC，来自 VCCA_3V3_S0 | 两版 p20 Audio Power、p32。这是网名/标称电源，不是实测 |
| 功放 | U7400/U7401 均标 AD51652/TCS7191A_MH，旁注还给 XA2613/TCS7191A 增益公式；实际装配型号待 BOM/丝印确认 | 两版 p33 |
| 功放电源/使能 | VCC_SPK_AMP 经 R2419 0Ω 接 VCC5V0_SYS_S5；SPK_CTL_H 接两片 pin1 EN，GPIO2_B1，高有效，100 kΩ 下拉 | 两版 p20/p33/p17；K7 DTS 42 |
| 静音时序 | Linux speaker DAPM 上电前等待30 ms 再使能，下电先禁用再等待40 ms；codec 的 es8323_mute 仅 return0，不是真静音 | K7 DTS 44–45；rockchip_multicodecs.c 304–312；es8323.c 637–640 |
| codec 复位 | p32 无独立 RESET 引脚；官方软件 reset 向 CONTROL1 写0x80/0x00，不能冒充完成所有模拟通路配置 | es8323.c 98–102；p32 |
| 独立模拟麦克风 | J7001 pin1=MIC2P→LIN2 pin22；pin2=MIC2N→RIN2 pin21，1.25 mm 2-pin，焊脚3/4接地 | 两版 p32 |
| 麦克风偏置 | VCCA3V3_CODEC 经 R7014 100Ω、R7015 1.1 kΩ 到 MIC2P；MIC2N 经 R7016 1.1 kΩ 到地；C7019 4.7 µF 去耦；不确定接入话筒所需工作电压/极性时不得猜测 | 两版 p32。偏置负载电压待量测，不是“已测1.65V” |
| 耳麦 | J7000 PJ-382，CTIA Tip=L、Ring1=R、Ring2=G、Sleeve=M；MIC_INP_PHONE/HP_GND 经电容接 LIN1/RIN1；R7007 2.2 kΩ 提供来自 codec 3.3V 网的偏置 | 两版 p32；实体插座焊盘号/方向仍须对照 PJ-382 封装图，不能只按引线顺序接线 |
| 耳机检测 | HP_DET_L 插入时拉低；GPIO0_D3、SARADC channel3；DTS gpio active-high 是驱动逻辑属性，不改写物理低有效网名 | p32；K7 DTS 37–39/223–226 |
| 喇叭接头 | J7400 pin1=AUD_SPK1N，pin2=AUD_SPK1P；J7401 pin1=AUD_SPK2N，pin2=AUD_SPK2P；焊脚3/4接地 | 两版 p33；音频两线均由功放输出，负端不是地 |
| 喇叭负载 | 原理图未给扬声器阻抗/额定功率；磁珠1.3A标注不是喇叭额定值。具体Ω/W、允许功率、实际功放型号都待确认 | p33，保留明确阻塞项 |

源码路径表中的短名均指本目录 `sources/kernel-6.1/` 下原路径，完整 SHA/OID 在 evidence/linux-inputs.json。K7 DTS 是 `arch/arm64/boot/dts/rockchip/rk3576-kickpi-k7.dtsi`；pinmux 和 SoC DTS 在同目录；codec 在 `sound/soc/codecs/es8323.c`；声卡和 SAI 驱动在 `sound/soc/rockchip/`。

板版差异：两版 p16 的音频连接文字一致；p32/p33 的 ES8388、功放候选型号、偏置阻值与连接器极性一致，V2.0 增加 TP7000–TP7005、TP7400–TP7403 等测试点。p20 音频电源拓扑相同，另加 RTC 测试点；p17 有非音频 pull-up/摄像头网标变化，不能声称整板完全相同。保留完整文字 diff 和选页图，文字比较不能证明 PCB 实际走线/贴装一致。

建议捕获试验 profile：16 kHz、2×16-bit slot、MCLK=4.096 MHz、BCLK=512 kHz、LRCK=16 kHz。这是根据 DTS mclk-fs=256、es8323 coeff_div 的 4096000/16000 条目与 SAI 公式算出的请求值，尚未在板上测得。32-bit slot 会改变 BCLK；不能只凭 PCM 有效位宽断言 slot 宽。SoC 主时钟/codec 从时钟和无反相 I2S 作为候选要求，最终要核对 hw_params/示波器，不能凭 net 名推断方向时序已通过。

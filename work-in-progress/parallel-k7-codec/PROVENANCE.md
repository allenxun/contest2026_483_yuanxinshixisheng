# 配置来源与精确缺项

所有引用的官方Linux文件均在 `input/kernel-6.1/`，来自上一项已校验的14个blob，本次再次逐项验证SHA并保留完整原始文件/许可。`input/sources.json`记录来源路径、Git OID和SHA；上一项两版原理图结论只读复制为input/HARDWARE.md。不存在按来源不明的网上寄存器表生成默认代码。

| source_id/用途 | 来源 | 本轮可确认的事实 | 执行状态/缺项 |
|---|---|---|---|
| 1 / reset参考 | sound/soc/codecs/es8323.c 98–102；es8323.h 15 | CONTROL1=0x00，Linux reset写0x80再0x00，第一次write错误未检查 | REFERENCE_ONLY；本目标reset时序、掉电状态与读回条件未审核，不能作为完整初始化 |
| 2 / 身份与连接 | arch/arm64/boot/dts/rockchip/rk3576-kickpi-k7.dtsi 206–219；两版PDF p32 | ES8388在I2C3，7-bit0x10；兼容串回退everest,es8323 | 物理身份依据充分，实板ACK/装料/总线适配仍待主任务 |
| 3 / MCLK候选 | 同DTS 47/216；sound/soc/rockchip/rockchip_multicodecs.c 373；es8323.c 392–397 | 声卡mclk-fs256，初始12.288MHz可被按rate重设；系数表有4.096MHz/16kHz条目 | 4.096MHz只是16k请求profile，不是实测；codec从模式和具体BCLK/slot须确认 |
| 4 / 格式参考 | es8323.c 483–548、563–634 | I2S/极性/主从会读旧寄存器并改掩码；S16设置ADC iface字段；Linux还改DAC路径 | 不直接转换RMW，缺硬件可读寄存器/保留位语义、只录音是否需要DAC时钟、正确slot宽 |
| 5 / 模拟输入参考 | es8323.c 104–177及DAPM路由；原理图p32 | J7001对应LIN2/RIN2差分，驱动提供PGA/differential及左右数据选择 | 不能从Main Mic/Headset Mic软件标签推导最终位值；差分输入选择、偏置、PGA/ALC/ADC通道与时序未完成审核 |
| 6 / probe/电源参考 | es8323.c 643–684、761–831 | probe包含大量固定write及两处18–20ms等待、set_bias；多次write忽略返回 | 非默认执行序列；未确认哪些DAC/输出步骤可删除、何时ADC才稳定、断电/失败逆序清理 |
| 7 / 读回政策 | es8323.c 846–854及reg_defaults；es8323.h | Linux是8-bit reg/val，regmap有缓存与默认值 | 缓存读取不等于硬件可读性证明；默认read_count=0，不允许任何未经审核的硬件readback |
| 8 / 停止/静音 | es8323.c 637–640、set_bias；rockchip_multicodecs.c 304–312；原理图p33 | mute callback仅return0；功放另有GPIO使能 | 缺ADC停机、I2C退出、DMA/时钟关闭顺序及实际静音/安全基线；由独立QUIESCE端口承担，尚无硬件实现 |
| 900 / 模拟寄存器 | tests/test_codec.c 的plan() | 0x20/0x11/0x02仅用于读写/掩码故障测试 | SIM_ONLY，与codec实际0x20含义无关，不能据此生成硬件配置 |

还发现一处参考源码内部冲突：probe在es8323.c 811向0x35写0xA0，而同文件848的regmap.max_register为ES8323_DACCONTROL30，头文件定义是0x34。该write又未检查返回。这里只记录可见矛盾，不推断厂商期望或私改上限；主任务移植必须核对目标版本完整手册/勘误。

官方资料检索尝试：2026-09-10访问 `https://www.everest-semi.com/pdf/ES8388%20DS.pdf`（HTTP亦重定向HTTPS）均由网页工具返回Timeout fetching。没有取得可核实的厂家寄存器手册；搜索出现的第三方镜像未作为配置依据。此限制与上面的精确缺项一并保留，不以缓存搜索片段补全数值。

本轮交付的是**可执行、测试通过的事务引擎**加**不可默认执行的硬件参考配置**。完整录音序列仍待权威资料/板测，因此硬件ready不是已完成项；主会话可继续实现端口及审核计划，不必重写本事务层的错误/取消/独占机制。

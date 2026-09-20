# 官方喇叭/麦克风接续缺口与PCM统计候选

先阅读旧audio/codec HANDOFF、delivery与硬件资料；未重做原初始化引擎/PCM声道转换/USB包规划。新组件只有pcm_observer.[ch]，供未来3秒录音证据统计，不触碰codec寄存器或默认未就绪门禁。未访问SDK/COM8/I2C/USB/板子，未改他人/正式源码或日志。

## 接口核对

| 接口 | 已冻结资料 | 当前确认边界 |
|---|---|---|
| SPK1 | J7400 pin1 AUD_SPK1N、pin2 AUD_SPK1P | 双线功放输出，负端不是GND；对应功放U7400 |
| SPK2 | J7401 pin1 AUD_SPK2N、pin2 AUD_SPK2P | 双线功放输出，负端不是GND；对应U7401 |
| MIC | J7001 pin1 MIC2P→LIN2(pin22)、pin2 MIC2N→RIN2(pin21) | 模拟麦输入，偏置网络存在，实际话筒规格/极性/偏置电压未测 |
| FAN | 原理图p35独立FAN_VCC/GND、PWM2_CH5_M1_FAN控制 | 不是音频接口；没有按线颜色猜针脚方向/电压 |
| codec | 原理图ES8388，DTS everest,es8323驱动兼容 | 不是已确认实板芯片ID；I2C3 M0、7bit0x10 |
| 数字音频 | RK3576 SAI1 M0 I2S，MCLK/BCLK/LRCK/SDO0/SDI0 | 不移植旧I2S_TDM寄存器；Linux时钟/复位/DMA只作参考 |

用户照片只读查看并记录SHA，未复制照片。照片能辨认SPK1/SPK2/MIC/FAN区域；SPK2和FAN位置有插头，MIC标识旁小座似为空，但线束交叠，无法可靠追踪两个外设的全线或确认针脚。不能凭照片认定全部接对/接错，也不能凭颜色推断负载或极性。在任何后续音频使能前由主会话确认麦克风实际连接MIC、喇叭连接SPK1/2，FAN不作为音频接口。照片不能证明PCB版号/功放料号/喇叭Ω/W。

## 尚缺实现与低音量播放/短录音前提

旧交付已确认缺RK3576 SAI lower-half、CRU/PD_AUDIO/pinmux/clock/reset审核、I2C3有界事务适配、DMA循环缓冲/cache/中断与停机确认、NuttX音频上下层连接。此结论针对冻结资料，不宣称远端SDK全树绝无驱动。

codec事务引擎已经有错误处理/超时/清理；但默认ES8388 reference缺完整capture/播放模拟通路、读回掩码、增益、时钟/停止序列，KC_NOT_READY仍必须零设备访问。Linuxes8323_mute为no-op，不能视为可靠数字静音。不得改审核位或用SIM_ONLY计划强行进入硬件。

主代理后续应分阶段：功放保持关闭，核实身份/电源/话筒偏置/连接，再确认I2C3、SAI1时钟与实际slot，完整codec录音计划得到依据后，限3秒采集并等待DMA真实停机；帧数、溢出/欠载、两通道PCM需作为证据。请求profile16kHz、2×16bit、MCLK4.096MHz/BCLK512kHz来自旧DTS/系数推导，尚非板测值。

播放还要另外核对功放/负载、DAC通路、可验证的静音/增益和EN低→受控使能→恢复静音/EN低时序。先静音数字输出，再固定小幅短PCM试音；低数字幅度不自动保证低声压，功放增益/负载未核定不能给寄存器音量值。不得用扬声器试音通过代替麦克风capture通过，也不能把8kHz TTS改header当16kHz。新组件不产生播放命令，所有上述依赖仍在。

## 独立新组件：有界录音统计

旧audio_candidate.py负责声道/分块转换，未提供C端逐通道能量/削顶统计；本组件补这一小项。只接受PCM16LE交织双通道完整帧，每块1..4096字节且为4倍数，总计<=48000帧。只有实际采样率16kHz验证后48000帧才对应3秒；组件本身不推断时间或时钟。

统计每通道min/max、sum、sum_squares、peak、clipped（-32768/32767）、nonzero、总frames。均值为sum/frames、RMS平方为sum_squares/frames，由host解释，不在实时循环浮点sqrt。48k×32768²远低uint64上限，abs(-32768)在int32进行；无动态内存/递归/设备/日志。单owner，po_init后不能直接改字段；错误块和超量拒绝且不改变统计。po_complete要求可信预期帧数精确相等，不自动把“非零音量”判成硬件通过；静音、串扰、频响、真实采样率仍需别的证据。

测试实际编译运行新C源码：符号扩展、极值、能量、削顶、分块等价、错误输入不改状态、48000帧边界/截断完成检查；不执行旧codec测试或板端测试。run.py记录原始命令/stdout/stderr/哈希，并只读校验旧manifest交付完整性。接口未接入DMA或驱动，只能在真实稳定PCM缓冲由可信owner交付后调用。

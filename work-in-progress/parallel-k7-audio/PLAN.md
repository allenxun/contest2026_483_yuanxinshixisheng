# 驱动差距、方案比较与有界验收

| 方案 | 已有证据 | 仍缺的关键能力 |
|---|---|---|
| 板载 ES8388/SAI1 | 两版原理图与官方 K7 DTS 一致；SAI、codec 和声卡原始 blob 已定点取出 | RK3576 SAI lower-half，CRU/PD_AUDIO/GRF/pinmux审计，DMA0循环buffer、cache与中断、I2C3可靠访问、codec输入选择/增益/错误回滚、NuttX audio upper-half 接线 |
| USB 耳机/话筒 | overlay xHCI 支持等时端点分配、通用 ISO TRB；已有相机 IN 传输路径 | 具体设备描述符与UAC版本、AC/AS接口及altsetting选择、PCM格式/采样率请求、时钟同步/反馈、持续无缝IN/OUT调度、拔出/超时停止确认、audio lower-half桥接 |

检查的是统一项目 overlay 和 `artifacts/model-arena-20260910/.config` 快照，不能据此断言 Ubuntu SDK 全树没有通用驱动。该配置明确 `CONFIG_I2S`、`CONFIG_DMA`、`CONFIG_DRIVERS_AUDIO`、`CONFIG_AUDIO` 未启用，而 `CONFIG_USBHOST_ISOC_DISABLE` 未设置，即等时支持并未关闭。overlay 搜索未找到 RK3576 SAI/I2S/codec lower-half，USBHOST Kconfig 没有已接入的 UAC host 项。最终 SDK 存量与构建由主会话核对。

`usbhost_xhci_rk3576.c` 2714 的通用 xhci_isoc_setup 会发 ISOCH/SIA TRB；4733 可分配 ISO IN/OUT；不能说完全没有 OUT 基础。3825 的 k7_xhci_isoc_submit 则明确 `!info->dirin` 拒绝，仅面向2048包、每包4096字节槽的大批量 IN；注释承认批次间排空，不保证连续。3875 的 wait 在超时后保留 DMA 映射并污染端点以防迟到 DMA。音频应设计小型循环队列/服务间隔、状态计数、Stop Endpoint/完成确认，不能直接复用相机批次当作双向音频流。

USB class层还需根据 UAC 版本解析 AudioControl/AudioStreaming、选择非零 alternate setting、处理采样频率控制及同步类型；有反馈端点的设备需独立反馈处理，不能以固定每毫秒字节数覆盖所有耳机。[USB-IF UAC1规范](https://www.usb.org/sites/default/files/audio10.pdf) 3.3、4.5、4.6、5.2。NuttX 的音频上层与硬件下层有独立接口，USB host class 需要单独注册，不能由“相机能用”推出音频类可用。[NuttX Audio](https://nuttx.apache.org/docs/latest/components/audio/index.html)、[USB Host](https://nuttx.apache.org/docs/latest/components/drivers/special/usbhost.html)。上述在线资料仅用于接口背景，实际项目能力以本地锁定快照为准。

先做录音准备，保持功放关闭。这样首轮不依赖尚未确认的喇叭负载，也能独立评价采集链路。板载路线连接信息较完整，但 DMA/SAI 新移植工作较大；若主会话能提供 USB 话筒的真实描述符，可优先评估 UAC1 单一 PCM IN altsetting 的短录音原型，现有 IN 基础可能减少底层工作。未取得描述符前不推荐购买某款或宣称 USB 更快完成。

主会话后续有界板测建议（本会话没有执行）：

1. 先确认 PCB 丝印、U7000及U7400/1装料、麦克风规格；功放EN保持低。确认数字1.8V、模拟3.3V及偏置、I2C上拉实际电平。仅定址0x10做有界访问，不全总线盲扫；记录ACK/错误和电平。确认CRU/PD/复位引用及资源冲突后才写入。
2. 用单一16 kHz/2槽profile实现受限DMA缓冲；按HARDWARE.md请求时钟并量测MCLK/BCLK/LRCK，记录真实slot宽、极性、采样率和DMA地址/缓存范围。不能把Linux寄存器表直接套到旧I2S_TDM上；rk3576使用rockchip_sai.c。
3. 首次最多录3秒，静音环境与约定短语各一次，保存完整PCM、实际帧数、两通道峰值/RMS/削顶、DMA underrun/overrun与中断计数；每次总上界10秒。失败立刻停止提交，等待DMA停机确认，未确认则保持内存租约并由主会话处理恢复。是否听到音频不能代替帧数/时钟验收。
4. 正确选择J7001的LIN2/RIN2差分路径；LinuxDTS里的Main Mic/Headset Mic文字路由与物理LIN/RIN组合还需逐项核对，不按标签猜通道。验证后再选择左/右或明确混音。16 kHz原始录音交给ASR，先不加自动增益/重采样。
5. 播放要另确认功放和负载；先验证不使能功放的数字输出/零数据，再由主会话安排限幅、短时播放和静音时序。当前TTS输出8 kHz；要么验证8 kHz硬件profile，要么加入经频响/混叠测试的重采样器，不能把WAV header改成16 kHz。不把capture通路通过当作speaker已通过。
6. USB备选：先保存真实设备/配置/class/端点描述符，确定UAC1/2、接口数/alt、采样率和同步类型。解析器只读测试后再安排3秒IN录音；OUT与反馈单列测试。拔出/重插、无反馈/异常feedback、短包/错包、队列耗尽须保留失败证据；控制调用成功不是连续音频验收。

候选 `audio_candidate.py` 是主机纯逻辑：CaptureSession按已命名步骤调用抽象后端，未通过显式证据门槛不开始；每步骤失败/超时回滚到等待释放确认，busy不抢占。`Backend.perform/quiesce` 是待实现的同步边界，超时检测不能中断卡住的调用；实际backend必须在对象外保留DMA所有权直到退出。无任何寄存器访问或设备打开。

`Pcm16Channels` 支持同采样率、PCM16LE、mono复制/stereo取左取右或均值，处理跨块不完整帧并拒绝结尾半帧；不做采样率转换。`FullSpeedPacketPlan` 只验证同步UAC1、FS、1ms的PCM16包量算术（44.1kHz有44/45帧），主动拒绝async/adaptive/其它interval；不是描述符解析器、反馈算法或音频驱动。未覆盖高质量SRC、真实DMA缓存和线程调度，这些仍需实现。

官方 codec 参考表只保存为 `codec-reference-only.json`：reset/probe 写入来自原blob，带行号；没有手造寄存器值。但多次write不检查返回、mute为no-op、默认增益/通路未经板测，故没有生成可以直接写实板的初始化代码。真正 lower-half 需补每步I/O错误检测、读回和逆序清理、输出静音状态、时钟稳定等待及datasheet依据。

# 音频格式一页只读审查

结论：**当前 MIC 正常路径是一条串行接收 lane、两个 32 位 slot，不是单 slot mono 模式。LIN2/RIN2 是同一模拟麦克风的差分两端；两个 ADC slot 与新增 lane 数据是不同维度。不能依据样本为零或左右反相决定丢弃/混合。** 本报告固定源码，不宣称实板格式已验收。

以下链接均指本交付的原样快照，原始完整路径及 SHA256 见 inputs.json。

| 已核对事实 | 依据（快照路径:行号） |
|---|---|
| K7 J7001 的 MIC2P/MIC2N 对应 LIN2/RIN2；codec 有单一 ASDOUT。Linux 两个 PGA 的 Differential Mux 都可以选择 Line2 的 LINPUT2/RINPUT2。因此“一个话筒”不等于“只有一个有效 ADC slot”，也不证明两 slot 独立声源。 | input/09-K7_V1.1_20241211_SCH-p32.txt:36、137、151；input/08-es8323.c:307–316；input/10-guide-text.txt:789、863 |
| 正式 codec 初始化 0a=f0、0b=82；main 用 bits=32，覆盖 ADC 0c=10、DAC 17=20。官方 S32_LE 同样写10/20，4.096MHz/16k 系数是256、02。I2S 的左右 ADC 仍以两个 slot 串行传输。 | input/03-codec_duplex.c:17、73–80；input/02-k7sound_main.c:332；input/08-es8323.c:393、614–622 |
| CSR 编码0=一条并行串行 lane，编码1=两条；SNB 编码1=每帧2 slot。这两个字段不能互换。正常 pio 使用 CSR(1)、SNB(2)、SBW32、VDW32、FW64、FPW32、MSB first，lane0 路由 SDI0。名义 BCLK=1.024MHz、Fs=16k，是配置值而非实测频率。 | input/05-SAI-layout.txt:461–467、486–496；input/04-rockchip_sai.h:19、28；input/00-pio.c:130–142 |
| Linux 非TDM自动 lanes=ceil(PCM channels/2)，随后 ch_per_lane=channels/lanes；CSR配置 lanes、SNB配置 ch_per_lane。因此2-channel PCM通常1 lane，4-channel PCM通常2 lanes，每 lane仍2 slot。 | input/07-rockchip_sai.c:528–533、587–620 |
| RX2只是独立内部回环实验：保留 SNB2、改变 RX CSR为2 lanes。该实验仍每两次 RXDR 读记一个软件 frames；不能直接把这个计数当实际 LRCK 帧或四通道帧。它不改变普通 MIC pio 的 CSR1。 | input/02-k7sound_main.c:224、345–348；input/01-duplex.c:104–110、144–145、178 |
| MONO_CR 的 rx_mono_en=1才选择单 slot；reset0是普通模式，rx_mono_slot_sel另行选择。当前 duplex要求MONO_CR=0；pio只读观察该寄存器，未启用mono。四FIFO计数的求和不说明四lane有效，也不证明RXDR交织次序。 | input/05-SAI-layout.txt:539–553、766–771；input/01-duplex.c:92；input/00-pio.c:8–16、36；input/07-rockchip_sai.c:1813–1829 |
| SJM定义8–31位在32位FIFO内的左右对齐；当前VDW32，不能拿SJM=0推断24位右对齐。I2S EDGE_SHIFT1/VDJ_L/SHIFT_RIGHT2和官方一致；SHIFT_RIGHT2不是软件应再右移2位。raw数组不转换，统计按二补码signed32解释。 | input/05-SAI-layout.txt:477–484；input/07-rockchip_sai.c:434–436；input/00-pio.c:24–25、133–136、197–199 |

**仍未知／合法解复用前置：** 上述资料没有证明 CPU RXDR 在1/2 lane配置下的实际银行轮转、首次读取相位、与物理LRCK的对应关系。TRM对RXDR只说读取FIFO；Linux的DMA路径与计数求和不能替代PIO证明。额外lane若无连接，其值也不能先验认作恒零。原理图文本不能独立证明所有SDI1硬件状态；双ADC近反相的具体极性/模拟增益与FIFO位对齐仍需实测，源码signed32解释不是converter精度验收。

**下一项边界：** 保留完整raw及寄存器/时间/模式。只有已知编号数字图样或物理LRCK/SDOUT对应测量证明 `(lane,slot)→固定读取序号` 后，才按该固定映射解复用，并验证采样帧数和真实持续时间；不能按数值删零、盲目平均反相声道或维持错误采样率标签。确认左对齐signed32后才可选某一有依据ADC slot并取bits31:16形成PCM16；这一条件当前不替实板下结论。无补丁、无设备操作、无SDK运行或下载。

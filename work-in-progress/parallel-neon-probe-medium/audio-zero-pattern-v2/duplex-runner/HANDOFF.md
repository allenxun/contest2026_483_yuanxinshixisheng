# 完整有限 duplex runner 候选

`duplex.c/h` 提供独立 `dl_run`，不修改已有单向pio接口。input冻结本轮正式pio.c/h与实际使用的官方SAI头，SHA在inputs.json。复用该pio的寄存器profile、四FIFO计数、20µs divider等待和停止流程；将停止推广为TX/RX同时停并等两个idle，然后CLK/FS仍开时clear3，等待自清后停止CLK/FS。没有引入DMA、reset、功放enable或codec调用。

接入调用：构造dl_port，read/write/us采用现有按offset回调；amp_low必须是纯GPIO强制低并确认低的幂等回调，不能映射为原streams_started。显式prepared/common_clock_verified以及MCLK4096000；后者表示调用方已确认同SAI1共享CKR/FSCR主时钟，见上级loopback附录的TRM条件。codec维持mute，外部功放全程低。capture由调用方静态分配512个uint32_t，result也应静态（含两组64条轨迹），均不得重叠。

例：`dl_run(&port, 1, common_verified, 4096000, capture, 512, 128, &result)`。第一次128frames（8ms）；最大256frames（16ms）。结果frames只统计完整读回pair；tx_words是已入队数量，不声称全部传出。

行为：

- 参数/容量上限先验检查；硬件检查VERSION23073576、XFER0、STATUS两流/FS idle、DMACR0、IRQ四使能关、两FIFO空、MONO0、八slotmask0、PATH共享时钟来源。硬件状态未知或拒绝时held=1，不能据失败自行断钟。
- 配置双I2S32/shift2、16k、单lane双slot；PATH只改00fc0303 mask，默认e4e4→4e4e4并检查原值/写后值。配置每项读回错误均拒绝进入流。
- 开CLK/FS，16word预填，sum4必须精确16。一起开启TXS/RXS；原字固定8个互异低幅标记循环，含每word前后FIFO和时间。无原PIO的activation/poststart hook，特别不会enable_amp。
- TX FIFO<=14才补2word，最大入队16；总写入另限2*(frames+16)，即使RX失效也不会无限输出。RX所有原字含零保存。前64次TX/RX访问在固定内存保存，不实时打印；诊断读失败直接判失败。deadline为frames/16000+5ms，poll预算4096/frame。callback本身必须非阻塞：软件无法打断一个挂住的MMIO回调。
- 收满指定帧立即结束，不等TX drain，余下预填标记在stop-clear丢弃。这是有限内部链路探针，绝不把未发送的尾部计作完成或用户音频。没有改变原单向PIO终止逻辑。
- 退出先force/verify amp低，保持CLK/FS直到两流idle和CLR完成；停止最多2ms（原PIO同等待预算）。只有stop成功才masked恢复旧PATH并读回。stop/restore/amp错误保留held，调用方不得进一步SAI访问或常规平台断钟清理。成功也保持外部MCLK，由调用方沿用至少2 BCLK再gating规则。PATH之外profile留作诊断设置，下一普通调用必须重新配置，不把它当透明共享驱动。

O0/O2真实主机执行通过，严格C11/-Wall/-Wextra/-Werror。原命令/返回值runs.json，原始输出compile-O*.txt/test-O*.txt。模拟通过256frame完整标记；模拟三零相位仍原样保存并特别标注传输0不是内容验收。覆盖容量/公共时钟/DMA/功放门禁、RX读错、时限、stop/clear卡住、PATH恢复失败、PATH读回不符、启动写失败。模拟器只验证软件协议及清理，不模拟真实RK3576银行语义。未交叉编译/未上板。

判读边界：必须同时看TX入队银行和RX银行，八标记不能先验命名银行0..3。若内部仍三零相位，codec ADC不是必要条件，但仍可能是TX端布局；内部完整也不能排除TX/RX相同错误抵消。以原始capture与trace为主，不自动对齐丢零/重采样。

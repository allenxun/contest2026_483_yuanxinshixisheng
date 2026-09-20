# PIO v2：三hook、16word预填与3秒录音上限

独立新目录，v1未修改。调用方式改变为 `pio_run(port,prepared,mclk,playback,capture,capacity_words,frames,&result)`；root统一MMIO/codec集成，候选未执行设备或SDK操作。

启动顺序：配置SAI（保持TXS/RXS关闭）→开启CLK/FSS→clocks_started调用B的kd_arm（codec I2C及30ms等待，amp保持低）→TX预填16word/读回必须16→启动目标TXS/RXS→streams_started调用kd_enable_amp纯GPIO→开始采样deadline和轮询。capture的streams_started应由root/B保持amp低，不是录音必然开扬声器。

退出顺序：amp_off_fast纯GPIO先关功放→SAI stream stop/idle→FIFO clear→FS/CLK stop/idle。该hook不能进行I2C、延迟或codec事务；codec I2C静音与完整关断由root在本函数返回后执行。正常/采样错误/中途配置错误都会走fast-off和stop；预检失败零配置写时不调用hooks，由root控制已存在的状态。kd_arm或enable失败也走fast-off/stop。`held=0`只证明本函数amp-fast-off与SAI stop成功，不证明codec事务已清理；root仍必须调用B cleanup并合并其错误，不能把PIO held当codec资源释放许可。

clocks_started回调必须有界100ms，streams_started与amp_off_fast各<100us。函数在返回后检测耗时，不能中断挂死回调；这些上界由B/root实现保证。read/write/us也必须有界且不阻塞、不打印。单owner，无DMA/IRQ用户，无重入。MMIO回调需设备顺序保证。所有v1电源/pinmux/时钟/codec raw32与VERSION23073576前置条件保留。

TX预填8帧=16word，仅在TX未启用时进行。记录result.prefill_words及max_fifo；预填不是16或其他lane有count报错，运行中观察count>16也报错。循环count<=14才补一对左右样本，不再等空；写后预计不超过16。物理至少16槽的依据仍是官方TDL16/RDL16/maxburst8的驱动配置推导，现版本额外要求实读16作为该次可观察佐证，而非仅凭6bit字段猜容量。预填最多约0.5ms音频余量，调度暂停仍可能欠载；INTSR错误不掩盖。最大样本数是入队帧数，结尾等FIFO空再stop，仍需真机判断最终声学尾部。

port.amplitude由root指定，必须1..2^27；正负signed32左右同值250Hz，2^27约-24.1dBFS，数字幅度不是最终声压保证，首板应由root结合已确认codec/amp增益选择更小值。播放frames8..3200（最多200ms）；录音frames1..48000（最多3秒），capacity必须>=2*frames，最大384000字节。root首轮3200，成功后再48000；本组件不会自动重试或延长。两方向仍分开运行，不支持双worker同时duplex。

采样deadline在streams_started返回后起算，frames*1e6/16000+100000us；另4096*frames轮询硬上限，最大196608000，无32bit乘法溢出。不再固定100000次造成快核过早超时。停止沿用最多2ms与有限poll，codec前置hook不消耗采样预算。raw capture仅result.frames个完整帧可消费；pio_summarize统计上限同步扩到48000，int64 sum边界安全。转换WAV由root离线对原始32bit对齐证据处理，此目录不猜ADC低有效位、不访问文件/设备。

复现本目录`python run.py`。真实MinGW GCC C11 O0/O2严格警告编译和寄存器模拟测试通过，test-output.txt保存命令/输出/exit。模拟证明arm期间无FIFO写/流、arm后预填16、stream后amp hook、实时模拟FIFO入队不超过16、3200帧TX/48000帧RX、hook错误清理、amp-off失败held、停止失败held、超时与参数上限。模拟不证明真实速率、pad/功放延迟、FIFO深度或声学输出。输入包含冻结v1源码/头/说明与其源manifest，保留追溯；outputs.json覆盖本交付。

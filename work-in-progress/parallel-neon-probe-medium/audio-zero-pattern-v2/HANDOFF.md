# 零相位复核 v2

结论：尚未定位根因；没有足够文档依据提交 RDE/CSR 寄存器修复。只交离线复核器和下一步可证伪的观察方案，不改取数、不删零、不启 DMA。

本目录 input 保存 16 项真实输入副本，inputs.json 固定 SHA256；正式源码快照仅供核对，不是修改建议。运行 `python analyze.py`，实际主机执行返回 0，原始输出 test.stdout.txt，结构化 results.json。复核原始串口 dump 的连续偏移、96000 个 word 与 WAV 逐字节相等；检查 32 次 FIFO before/after 真实消耗。没有目标编译或设备操作。

## 已确定

- PGA24 最新 48000 帧：左非零相位计数 [12000,0,0,0]，右 [11999,0,0,0]。右相位0存在一个真实零，不能要求每个有效样本都非零。
- 32 次 trace 每两次读对应一个银行，0→1→2→3循环；银行1/2/3确有 entry 从2→1→0，不是空读。相邻 pair 约62–63µs。48000 pair 总窗3000041µs。
- TRM SAI-layout.txt 639–654 定义每银行有效 entry 数；766–771 仅说 RXDR 读取访问 receive FIFO。未提供 CPU bank-select 字段、CPU轮转算法或“读一次推进多少lane”的额外契约。寄存器总表的 W 是宽度项，不可据此把 RXDR 当只写。
- TRM 455附近 RXCR 的 CSR=0 表示单并行通道，SNB编码1为每帧2slot；不是总共8声道的授权。不能由四银行状态直接推导4lane启用。Linux rockchip_sai_get_fifo_count 第1813行起确实求四银行总和，因此不能简单只读bank0或忽略其余计数。
- Linux rockchip_sai_start 第396行先打开DMA请求再启动；capture DMA地址固定RXDR，宽度4bytes（1207–1209），hw_params maxburst按声道数计算（550）。这些说明已支持路径使用DMA，不证明PIO路径和DMA路径具有相同内部排序。
- TRM 665–676只定义RDE开启接收DMA及RDL请求水位；没有“RDE改变bank路由/CSR生效条件”的说明。缺RDE是可疑路径差异，不是已证实原因。不得直接开请求作修复，也不能声称无DMA channel即绝对无风险。
- 官方 es8323.c 第393行明确 4096000Hz/16000Hz/256fs → sr=2,usb=0；hw_params 第590–630行写分频与S32接口。真实回读08=00、0c=10、0d=02、17=20、18=02与该配置一致，没有误用1024fs的寄存器证据。软件MCLK公式4.096MHz成立不等于外部引脚实测频率成立。
- observe.c 的第三观察位是GPIO4A5/LRCK；日志20ms内640次变化支持16kHz LRCK。该采样器仅统计变化，不能解码1.024MHz BCLK或4.096MHz MCLK：max_gap35个24MHz tick约1.46µs，可能漏高频边沿；GPIO输入all-high也不能替代运行中同步SDI位流证据。

## 已关闭的解释

空FIFO读取、dump四倍扩张/字宽错误、仅波形随机静音、输出脚MCLK完全未开、已知PATH路由不正确、slot mask、MONO、CSR/SNB读回错误均不符合现有证据。H/M reset与20µs等待未修复，由主会话实测报告支持；本轮没有重跑这些实验。CLKFS关闭时start-clear超时原证据仍保留，不能重试相同方法。

## 新的区分性观察（未执行）

1. **区分“读访问推进银行”与“接收入队独立轮转”**：现有trace总是及时把pair读空，无法判断银行序列与CPU访问之间的因果。可在同一配置、稳定接收后，仅一次暂停RXDR读取250µs，期间只保存时间/INTSR/RXFIFOLR，然后保存前8次RXDR读取的每银行before/after。不写任何新寄存器，不改CSR/codec/DMA。TRM每FIFO32深，现有16k双word模型250µs约8words；这只是预估，须保持原RXOI拒绝、总deadline和最多8次额外trace，观测异常即按既有stop退出。
   - 暂停期间银行已自行轮转/多银行积累，排除“仅RXDR读取动作才推进银行”的简单模型。
   - 暂停期间只bank0积累、随后读取使其他bank出现，则支持CPU访问相关序列，仍需硬件PIO契约确认；不能直接删其他bank。
   - 该诊断不证明DMA会修复，也不判定codec输入质量。没有提交设备代码，避免把假设当必需寄存器操作。
2. **同步输入证据**：短窗同时获取实际codec SDOUT/SAI SDI0、LRCK、BCLK，逐帧解析I2S的1bit延迟及双32slot，保留四相位零。若线上每帧数据均存在而RX仅phase0有效，定位到SAI取数链；若线上已3/4帧严格零，转查codec/物理时钟。该证据须同步，分别数引脚边沿或听声不能替代。MCLK计频确认256×LRCK，可证伪时钟比率问题。
3. 若无法取得上述观察，应索取23073576版本PIO的RXDR银行选择/CSR有效条件与DMA握手关系的明确硬件说明。不要改为CSR=3或启动DMA来掩盖未知。

## 验收边界

这里只验证数据完整转录和异常模式，不验证16kHz有效音频质量、ASR、滤波正确性或录放正常。尚无源证据支持修复寄存器值；因此没有猜测性的patch。暂停取数方案须由主会话决定是否集成为独立显式诊断，不能默默进入普通录音路径。

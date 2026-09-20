# PIO runtime boundaries

本轮冻结当前正式源码（inputs.json），不重复四字段FIFO修复或codec路由审查。test_runtime.c直接链接冻结pio.c，模拟寄存器行为，不是硬件或音频正确性证明。

TX：当前先INTSR/TXUI判断，再FIFO，再frames==target检查。8帧预填后最后FIFO被消费且TXUI同时可见，实际函数返回-75，即使frames==8。这是可回放的逻辑边界，不证明真实硬件必在终点产生TXUI。中途欠载也返回-75，应继续拒绝。**不要仅把FIFO读放到INTSR前、或frames==target时忽略TXUI**：frames计数是已入FIFO数量，缺少物理输出计数时无法排除最后一批提交前/期间的欠载和移位寄存器残留。FIFO空也未必等于最后串行位已发完。建议root先保留真实尾部INTSR/FIFOLR/frames/硬件counter证据；需要优雅有限TX终止时依据精确SAI TX_DATA_CNT含义和TXS停止是否排完移位器再定方案，不猜计数单位或删除检查。此小交付不提供不可靠的“忽略终点错误”补丁。

RX：两次RXDR成功后才递增frames，没有memset/zero padding。第二字读失败时第一个真字可能写入尚未计数的尾槽，但root dump只导出2*captured_frames，因此不会把它作完整帧。测试用非零sentinel确认未采区不变。真实0样本应保留为0，不能伪造非零；同时“全0”不能仅靠数组初始值判MIC有信号。root保留rc、frames、raw words和统计，失败partial capture仍可用于诊断但不是完整验收。当前最后一帧读完会再循环检查一次状态才退出；终点后RX溢出也可能把已取得的完整前缀标失败，保守失败不是丢样或补零，暂不放宽。

调度：本命令CMake优先级100，当前主函数无显式亲和或调度策略设置，不能从源码认定总在CPU0；root应记录实际CPU、affinity、policy/priority。16个TX字在16kHz双声道下只有约500us预填余量，环内通常接近满FIFO；更长抢占足以产生真欠载。RX允许延迟由真实FIFO容量与占用决定，不能把四字段总数当已知硬件深度。3秒忙轮询即使在A72也会被更高优先级线程/IRQ抢占；CPU快不等于低最坏延迟。若CPU0干扰明显，可将本次PIO任务限定一颗经主线确认空闲的A72作对照，并记录CPU/计数器/错误率；不是前置硬要求，也不禁止调度或屏蔽所有中断3秒。不要在实时循环打印串口/每帧让出。长期唤醒/录音最终需要持续缓冲或DMA，不把3秒PIO当长期音频架构。

建议记录低开销max_poll_gap_us、首次/末次完整RX帧时间、TX/RX激活与数据停止时间、错误时INTSR及FIFO raw，退出后统一打印。这些指标用已改CNTVCT/CNTFRQ时间基准。时间超限应保留原始数据、完成STOP检查，不自动重试拼接出一段看似连续的录音。

采样率：dump头rate=16000是请求值，不是实测。48k帧墙钟约3秒仅粗验（初始FIFO积累、读取批次、启动hook和停止开销会偏置）。可以记录多个窗口中“累计已读完整帧+当前FIFO完整帧”之差/单调时间差，注明FIFO计数/声道配对与采样延迟假设；或者精确核实SAI硬件数据counter后取多窗口斜率。不要用每次RXDR间隔直接当LRCK周期。将原始PCM完整导出后，可用已知声学参考音/用户拍手验证有真实输入；未知语音不能证明绝对采样率。没有用户额外仪器也能报告设计16kHz+计数器粗估，而不冒充物理LRCK测量。

本次结论：无zero填充缺陷；TX尾部存在保守失败边界，不能凭单一frames数量改为通过；亲和作为有证据的对照实验即可。没有修改正式源码、SDK或设备。主机复现和原始结果见run-evidence.json。

## 可选最小错误现场补丁

diagnostic.patch只在TXUI/RXOI错误现场保存error_intsr、error_fifo_raw、error_fifo_valid，以及tx_tail_candidate。该标记仅表示当时所有请求帧已入FIFO且FIFO采样为空，不表示已无丢帧播完；返回码仍-75。中途尚未全部入FIFO时该标记为0，两者可在日志区分。FIFO采样晚于INTSR，非原子快照，保留这个边界；读FIFO失败时valid=0，仍保留原TXUI错误。root若集成需在循环外输出这几个字段，不能把candidate当known drain completion。

只有独立证据证明硬件已输出目标帧数且移位/帧同步已正确结束，才可另报known drain completion；这仍不是声学验收。目前没有核验硬件counter单位/边界，因此不自动生成该成功状态。正式冻结源与candidate各O0/O2严格C11回放通过，candidate测试确认尾部标记为1、中途为0且两者都失败。candidate-results.json保留原始输出。

测试开发记录：初次失败发生在mock RX读取错误时它先覆写输出指针，sentinel断言不成立；改为该故障回调失败前不改输出后通过。这不是生产PIO补零。首次MinGW assert进程未退出，核实其本目录exe路径后终止该单个进程；随后改为显式stderr+exit断言并为编译/运行设置20秒上限。未终止其他任务。最终记录覆盖最终测试源码，不声称初版一次通过。

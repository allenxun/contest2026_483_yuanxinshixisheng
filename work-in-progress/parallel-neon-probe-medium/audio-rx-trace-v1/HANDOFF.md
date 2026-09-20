# 前32次RXDR只观察轨迹候选

基于本目录input中固定快照的正式app/k7sound/pio.c/h，最小rx-trace.patch只加诊断数据与观测，不修改FIFO总和、取数阈值、丢零规则、sample数、TX收尾或codec顺序。没有设备/SDK/正式源码/其他候选操作。

pio_result新增rx_trace：固定32项entry，字段time_us/fifo_before/word/fifo_after与before_rc/word_rc/after_rc；count表示尝试读取RXDR的已记录次数（包含原RXDR失败的一次）。原始RXDR仅执行一次并直接写原capture槽，再拷贝成功字到trace，零和0xffffffff均不特殊处理。超过32次后直接走原rd路径，不增加后续FIFO观测。原RXDR失败仍返回原错误并终止；额外FIFO观测失败只将对应rc标-5，不改变原样本是否接受，消费者不得把失败项的零初始化值当硬件读数。

窗口start_us在目标stream启动hook返回后、第一轮之前；同时顺序记录init[6]/init_rc[6]，固定顺序为MONO_CR0x0c、RX_SHIFT0x68、RXCR0x08、PATH_SEL0x38、DMACR0x24、XFER0x10。此时是active配置快照，非原上电初值。各寄存器不是原子同时采样。end_us在所有传输尝试结束、ampoff和stop之前；window_started用于区分根本没进入取样窗口的早期失败。time_us是该次FIFO-before读前时间，绝不把它冒充严格总线采样沿。

root应在stop/cleanup后统一导出：窗口起止、6寄存器及rc、count条entry，每条打印index/time/rawbefore/rawdata/rawafter与3个rc。不得在实时回调打印。该诊断给出RXDR是否伴随计数字段下降及零字位置的证据；没有增加second RXDR确认读，也没有丢弃或压缩0。数据缓冲顺序/内容与原路径一致（在同样模拟输入下验证）。

额外每字2次FIFO读和一次time读、开始6寄存器读会改变前32次的取样时序；不是完全无扰动仪器，不宣称它证明原版本所有时序。窗口时间足以比较实际采集持续时间与frames标签，但CPU任务调度也会影响耗时。回调必须保留原有有界/设备读顺序条件。

内存固定约1.1KiB额外result结构，无分配/全局共享状态；root需检查实际目标sizeof与k7sound栈配置，或将result置单owner静态存储。结构布局改变须同步重编译调用者，不能拿旧ABI的result内存传新函数。

`python run.py`在真实MinGW GCC C11 O0/O2严格警告下编译运行通过。test-output.txt保存命令、模拟轨迹摘要和退出码；所有源/补丁/原始输出有SHA256。测试固定产生每8word两项ffffffff后六项0，逐字验证capture与trace保持原样、32项上限、时间递增、初始化寄存器、诊断FIFO读失败标invalid但不减少样本、短1帧只记2条，并保留既有tone/buffer/capture边界回归。测试向量明确模拟，不冒充真实麦克风内容。没有新ARM或实板结果。

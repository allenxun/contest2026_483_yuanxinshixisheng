# PIO v3：按官方算法汇总四个FIFO字段

已冻结当时正式app/k7sound/pio.c、pio.h、SAI头与Linux官方rockchip_sai.c/h，inputs.json记录SHA256，input保留字节。没有修改正式源码、SDK或设备。最小补丁fifo-sum4.patch仅修正计数解释及诊断字段，不修改时钟、codec、CSR、样本格式或功放hook。

## 可判定根因与未知

root报告实板VERSION23073576；tone写16次TXDR后pio=-71、frames=0、max_fifo=4；capture返回-71、frames=1、max_fifo=2。旧代码max_fifo只取低6位并把bits6..23全部视为非法。这与官方rockchip_sai_get_fifo_count（冻结rockchip_sai.c:1811–1829）不符：官方始终相加XFL0[5:0]+XFL1[11:6]+XFL2[17:12]+XFL3[23:18]，不按CSR或lanes过滤。四字段mask/shift来自冻结原头。

因此确认软件错误是错误地只接受XFL0。日志没保存完整raw寄存器，不能证明当时“四字段各4”，更不能据低字段4断言“一单位=4word”。v3不乘4、不变更CSR、不猜128bit packing。模拟raw0x104104（四字段各4）只是可解释观察的测试输入，不是重建未知实帧/寄存器。CSR描述串行lane数量，不提供过滤FIFO字段的源码依据。

## 修复及统计单位

新增pio_fifo_count按官方四字段求和，范围0..252；忽略未定义高8位，不将其当已知错误状态。预检残留、预填、运行TX/RX和TX结尾均使用同一total，不能只修TX预填一个点。TX预填仍必须严格total==16；如果完整raw确实只有0x4，仍-71并禁止启流。16个32bit写与total16的停流预填检查是本次操作的计数一致性证据，不是对所有格式/全芯片版本的深度证明。

max_fifo现在表示四字段聚合的计数（不再是XFL0）；prefill_words仍为真实成功TXDR写次数。新增first_fifo_raw/last_fifo_raw保存完整32bit寄存器，不进行字段改写。TX first为预填后值，RX first为第一次循环观察，可能为0；last为最近一次成功FIFO观察，失败时也保留。root日志应打印上述两个%08x以及max_fifo总数，避免下次丢单位证据。

TX当total<=14才写一对样本，观察total>16仍报-71；最多16个已知排队word目标不变。RX当total>=2才读两个32bit word，聚合来自任何字段都不再被误判为非法。每完成一对read/write才frames++，没有将FIFO计数直接当帧数。TX入队够frames之后继续等total==0，随后沿用ampoff/stream-idle/FIFO-clear/FS-idle清理，不以低字段0冒充所有FIFO空。总计数零仍不独立证明声音到达扬声器，stop完成也不是端到端声学成功。

raw32、VDW32、slot32与左右顺序未在本补丁更改。官方S32_LE+4byte DMA支持原路径，但PIO rawword与真实ADC对齐/左右仍需root捕获数据确认。此次sum4修复不把全零第一帧归因麦克风，也不证明PCM payload已有效。

## 测试与交付

本目录`python run.py`在MinGW GCC C11 O0/O2及Wall/Wextra/Werror/pedantic下真实运行通过，日志test-output.txt。包含：四字段分布预填raw0x104104/total16成功、RX raw0x41/total2成功、所有字段最大sum252、保留位不计数、单字段16仍16、完整raw4预填依然拒绝且没有启流；保留v2 hook顺序、FIFO<=16、3200帧TX/48000帧RX、清理错误与时间/容量边界测试。

模拟采用可控分布器实现FIFO计数，证明软件遵守官方聚合算法，不是硬件bank布局验收。输入冻结后若正式文件改变，run.py明确拒绝覆盖旧input；可仅对冻结候选执行日志所列编译命令，更新交付哈希用seal.py。没有ARM交叉编译或新真机结果。接入由root独占，先看新完整raw与total是否满足严格检查，再开展声音确认。

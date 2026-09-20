# TRM与复位路径补充（等待真实trace）

只读冻结SAI-layout.txt及其input.json，保留PDF来源SHA256 6094ae5874d8494e73fa363d9cf35dd65acbd54a9a9d633b1ba5e4bea289f0a8。来源manifest实际start_zero_based=921/end_exclusive=948；不把口述pages922–937当精确提取范围。本次未访问设备或SDK。

1. TRM明确八个内部FIFO，四TX四RX，每个32bit宽×32entries深。FIFOLR四6bit字段分别给对应FIFO有效entry数；TXDR0x30/RXDR0x34寄存器表W=32bit访问。所以过去“深度至少16”的推导可由这条精确TRM证据替换为每FIFO深32；当前保守总量16上限仍可保留，不必为了排查扩大。不存在从此文档支持“一count单位128bit”的证据。

2. TX TDL段明确CSR00使用FIFO0水位、CSR01使用FIFO1、CSR10 FIFO2、CSR11 FIFO3。TX/RX CSR段说One/Two/Three/Four channel parallel。已知实际16次TXDR写后raw00104104=(4,4,4,4)与预期单通道只FIFO0的简化假设不一致，但TDL只是DMA请求水位判定，并未规定CPU write入哪个bank或轮转指针的配置规则。不能从TDL直接推“所有非0bank必须无数据”，也不能用SUM16就断言PIO通路已完全正确。

3. 当前RXCR00400fff解码CSR00、SNB两slot、32bit仍与Linux hw_params匹配。TRM在若干字段注明只能在XFER特定位为0时写；本candidate已先拒绝CLK/FS/TX/RX活动再写格式。但TRM RX说明写条件XFER[2]，而同章节XFER[2]定义TXS、[3]才RXS，文档有索引描述不一致；不能用这句话单独证明寄存器未锁存。实读格式值只能证明APB侧寄存器值，不独立证明跨时钟域FIFO状态机使用了该值；后者需要对比trace或厂商明确同步机制。

4. 冻结Linux rockchip_sai_probe约1873/1877仅取得optional exclusive H/M reset控制句柄，没有调用assert/deassert/reset。真正rockchip_sai_reset仅在rockchip_sai_clear的超时分支调用：H assert→10us→deassert→10us，再M assert→10us→deassert→10us，随后regcache_mark_dirty/sync。其注释说明先H再M用于slave无输入CLK时M域reset困难。故不能声称Linux probe总是复位而当前平台漏做了必需动作。

5. 显式H/M reset可以由root在独占SAI、codec mute/ampoff、确认DMA/流已停且保留原值的独立实验中评估；它必须重新应用全部格式/路由/计数相关初值并记录reset前后。此建议不是已证实修复，也不等于允许在未知活动状态强制reset。不改变CSR、不删除样本中的0；先保留当前32读trace，避免reset掩盖可复现初态。

优先判别依据：每次RXDR读前后四FIFO字段是否递减、零字对应的bank状态、MONO_CR/CLK/RXCR初值及真实start/end时间。若零字读取并未消耗有效FIFO entry，就应追踪CPU数据窗口/轮转语义；若零字也正常消耗entry，则需追踪串行slot来源/未启用输入线。当前TRM段未给出足够细节把这两类合并为一个确定根因。SUM算法保留其官方来源，但不能代替有效音频样本证明。

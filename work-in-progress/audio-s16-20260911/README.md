# S16 音频单变量实验

当前真机 S32 stereo-slot 路径以 16 kHz 采集时，`RXFIFOLR` 四个字段轮流提供数据，但仅第一组包含有效音频，形成每八个 MMIO word 两个有效、六个零的规律。250 微秒停止读取 RXDR 时四个 FIFO 各自积累两个 word，排除了只有 CPU 读操作才推进 FIFO 的简单解释。

本实验新增显式 `k7sound capture-pga24-16`，同时把 ES8388 ADC 接口、SAI VDW/SBW、FSCR 和 CKR 切到一致的 16-bit stereo-slot 配置：MCLK 4.096 MHz、BCLK 512 kHz、LRCK 16 kHz。Linux codec 驱动的 S16 分支写 ADC interface 0x0c，项目 codec 组件已有同样实现；项目固定 SAI 配方期望 RXCR 0x00400def、FSCR 0x0100f01f、CKR 0x38。

现有 32-bit capture、tone、replay 和 pause250 路径保持原配置。S16 采集用 32-bit MMIO 容器保存左对齐的 signed16 数据，可交给现有 float 转换；为避免格式错误，S16 捕获明确禁止走现有 S32 replay。主机 O0/O2 覆盖旧 PIO、暂停诊断和新 S16 寄存器值；真机尚未验证。

本轮不写 eMMC/STM32，不启动执行机构。仅在 S16 真机原始非零分布、停止/恢复和实际 ASR 都通过后，才考虑替换默认采集格式。

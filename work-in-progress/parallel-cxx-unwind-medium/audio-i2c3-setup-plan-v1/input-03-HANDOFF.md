# I2C3 read-only audio preflight

本轮仅建议读取以下 8 个 32-bit 对齐系统寄存器，各一次并保留原始值；不读 I2C、codec、SAI、GPIO 数据/方向寄存器，不写门控、复位或 mux。地址是来源推导的候选白名单，主会话仍须确认当前固件 Device 映射和访问权限；源码不能证明当前安全域/电源状态下所有访问必定完成。

| 地址 | 名称 | 低位字段解码 |
|---|---|---|
| 0x272003e4 | CLKSEL57 | mask 0x30，shift 4：0 clk_gpll_div6；1 clk_cpll_div10；2 clk_cpll_div20；3 xin24m |
| 0x27200830 | GATE12 | mask 0x4 PCLK_I2C3；mask 0x4000 CLK_I2C3；各位 1=门控关闭，0=未由该门关闭 |
| 0x272003dc | CLKSEL55 | mask 0xc，shift 2：PCLK_BUS_ROOT 父项 0 clk_cpll_div10；1 clk_cpll_div20；2 xin24m；3 未定义，应标 unknown |
| 0x2720082c | GATE11 | mask 0x2，PCLK_BUS_ROOT；1=关闭 |
| 0x27200300 | CLKSEL0 | clk_cpll_div20：parent bit5 mask0x20，divider bits4:0 mask0x1f；clk_cpll_div10：parent bit11 mask0x800，divider bits10:6 mask0x7c0 |
| 0x27200304 | CLKSEL1 | clk_gpll_div6：parent bit11 mask0x800，divider bits10:6 mask0x7c0；本轮忽略其余位 |
| 0x27200800 | GATE0 | div20 bit0 mask1；div10 bit1 mask2；div6 bit3 mask8；1=关闭 |
| 0x2604408c | GPIO4B high iomux | SDA GPIO4_B4 mask0xf shift0；SCL GPIO4_B5 mask0xf0 shift4；各 0xb 表示 I2C3 M0；0 表示 GPIO；其他值仅报告数字/非 M0 |

这些 HIWORD_MASK 寄存器的高16位为写掩码机制，不把读回高位当第二组状态。无写操作，也不构造 mask 写值。读到 mux=0xbb 仅证明选择功能，不能证明线路空闲、上拉、电压、电气连通或 codec 响应。

## 来源与频率边界

冻结 clk-rk3576.c:274–276 定义 HIWORD 与 SET_TO_DISABLE；:282 给 GPLL/CPLL 顺序；:309、313 给 PCLK/I2C 父项；:404–415 给可编程父分支；:561–563 给 PCLK_BUS_ROOT；:583–584、609–611 给 I2C3。CRU base 与偏移依据冻结 k7radio_main.c:32、39、41，当前 rk3576_boot.c:68–71 已列 IOC/CRU Device 映射。DTS 为资源交叉证据，不把 Linux 初始化状态沿用到 NuttX。

**200/100/50/24 MHz 只能称 nominal 标签，不能从 CLKSEL57 直接得到真实 Hz。**前三个父分支是 COMPOSITE，不是固定 factor；其 parent bit=0 GPLL、1 CPLL，divider 按常规字段值+1（该源 DFLAGS 只有 HIWORD，没有 one-based/power-of-two）。因此功能频率应为选中实际 PLL rate / (divider_field+1)，还要核查该分支 gate；PCLK 同理。分支名字中的 div6/div10/div20 不保证当前分频值。xin24m 也仅为父名/标称，不是本次物理测量。

此最小清单不含 PLL mode/bypass/lock/整数分数反馈或参考源寄存器。缺少完整、同一时段、经精确 PLL 算法解释的输入链，输出 actual_rate_known=false，禁止自动将 nominal_hz 喂入 timing 候选。Linux 驱动使用 clk_get_rate(i2c->clk)，不是从父名解析数字。若另有已核验的 clock provider，可记录其来源/时间；软件推导 rate 与物理测量 rate 仍分开。门控为0也不能证明 PLL 锁定、复位释放或正在输出稳定时钟。本轮应当允许“读数完整但尚未就绪”的诊断结果。

## 门控与读取边界

I2C3 PCLK 关闭、上游 PCLK root/所选分支关闭或未知时，不访问 0x2ac60000..0x2ac60fff 的任何控制器寄存器，包括 CON/version、CLKDIV、IPD、FIFO；不能用尝试读取来探测是否安全。冻结 i2c-rk3x.c:1017 起在访问 CON/CLKDIV 前先 clk_enable(pclk)，支持接口时钟是先决条件。功能 CLK_I2C3 关闭与 PCLK 关闭不是同一个状态；仅功能关闭未必使 APB 不可读，但不能据此批准本轮外设读取。当前任务无论 gate 读数如何都跳过整个窗口。

IOC mux 寄存器属于 IOC 系统窗口，非 GPIO4 控制器窗口，不需要通过读 GPIO 数据来解释；I2C3 的门控不等于 IOC 门控。这里没有证明 IOC/CRU 自身所有上游域永远开启，因此须依靠主会话已核验的系统映射/电源访问前提；条件未知则 skip/not-ready，不开门、不解除复位。GPIO、SAI、codec I2C 访问均不在白名单，不做寄存器遍历或泛化 dump。

pin 地址推导：冻结 pinctrl-rockchip.c:5238 bank4 B offset0x4088；:1136–1142 4-bit 且 pin%8>=4 再加4；IOC base0x26040000，因此 B4/B5 为0x2604408c 的低两 nibble。冻结 rk3576-pinctrl.dtsi:1715–1720 明确 B5 SCL、B4 SDA、mux11。报告 mux 不自动重配它。

## 接入与交付

建议 root 输出每项 address/raw32，再输出门控位、selected_parent、divider_raw、mux_sda/mux_scl、actual_rate_known=false、peripheral_reads=0、writes=0；绑定固件哈希及原始串口文件。writes=0 需源码/构建审计支持，不能仅依赖自报。拒绝任意地址参数；读取前确认 MMIO 地址空间，发生异常停止，不重试读未就绪外设。本交付只读源码审查，无目标读数、无硬件测试、无寄存器操作。

inputs.json 固定所有输入的字节数、SHA256 和原路径，各 input-* 为原样快照。delivery.json 给交付哈希。旧 adapter HANDOFF 中 parents 200/100/50/24MHz 应按本报告补充理解为标称名称，旧证据保持不改。

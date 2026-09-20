# RK3576 SAI 周期零样本：RDE/RDL 独立审查

## 结论

周期零样本的根因仍未定位。现有证据已把问题收窄为 SAI 接收端的数据组织/路径问题：`RXDR` 读到的零不是对空 FIFO 的误读，而是 FIFO1、FIFO2、FIFO3 中有计数的真实条目；无 `RXDR` 访问时四个 FIFO 也会自行积累；内部数字回环仍复现相同周期零值，因此麦克风和外部 ADC 不是复现所必需。

`DMACR.RDE/RDL` 联合实验的解释力有限。TRM 只定义 RDE(bit24) 为接收 DMA 请求使能，RDL(bits20:16) 为请求水位字段；没有说明它们改变 CPU 读取 `RXDR` 的 FIFO 选择。Linux `rockchip_sai.c` 配置真实 dmaengine 的 RXDR 地址、4 字节总线宽度和 burst，再设置水位并在启动时打开 RDE。该驱动没有 CPU 循环读取 RXDR 的音频路径，不能用其 DMA 成功路径推出 PIO bank 语义。

当前 `audio-rde-20260911` 方案同时把 RDL 从旧值改为水位16并打开 RDE。若图样变化，无法分辨是 RDL、RDE 还是两者交互；若图样不变，只能在该版本、该 PIO 时序下削弱“请求门控会修复 bank 轮转”的假设。即使零值减少，也只证明存在模式耦合，不能直接称为修复或正确 16 kHz 音频，因为实验没有配置/提交/停止真实 DMA 传输。

## 证据链

- TRM `SAI_RXFIFOLR` 给四个独立 6-bit level 字段；`SAI_DMACR` 位24是 RDE，位20:16的编码值加1才是 RX 水位；`SAI_RXDR` 只写明读取时访问接收 FIFO，没有 CPU bank 选择规则。
- `audio-pause` 真机在 252 us 无 RXDR 读取后得到 `RXFIFOLR=0x00082082`，机械解码为 `[2,2,2,2]`。随后八次读取依次把 FIFO0、1、2、3各减两项；FIFO0两词是 `ffffffff`，其余六词为零。串口后半段有缺字，但这一完整前八词窗口足够支持该有限结论。
- `audio-rxtrace` 的独立早期真机记录给出相同的 level 序列：`2,1,0x80,0x40,0x2000,0x1000,0x80000,0x40000`；对应数据为两个非零和六个零。`trace_valid=true`。
- 内部静音数字回环128帧传输成功，仍有194个零词并保留周期图样。这排除了“必须有外部麦克风/codec 模拟输入才复现”，没有排除 SAI 内部 path/lane/FIFO 组织问题。
- S16 目录的 README 记录：真机读回 `RXCR=00400def`、`FSCR=0100f01f`、`CKR=38`，仍按固定四词周期仅一个有效词，3200帧请求在2399帧超时。因此把 slot/valid width 同时改成16 bit没有解决问题。审查时该目录没有 `board-result.json` 或原始真机日志；本交付将这条视为主会话摘要证据，未把它冒充为可独立重放的原始证据。O0/O2结果只证明主机模拟路径通过。
- Linux 头文件 `SAI_DMACR_RDL(16)` 实际写入字段15，即 DMACR bits20:16=`0x0f`，对应 TRM 的水位16。报告和板端日志应区分“字段值15”与“水位16”。

## 下一项最小实验

使用同一固件和同一128帧内部编号回环，做三臂、两步对照；每臂都从停止并清空的相同状态开始：

| 臂 | `DMACR[24] RDE` | `DMACR[20:16] RDL` | 用途 |
|---|---:|---:|---|
| A | 0 | 保留启动前字段 | 当次基线 |
| B | 0 | `0x0f`（水位16） | 单独检验 RDL 写入是否改变 PIO 图样 |
| C | 1 | `0x0f`（水位16） | 相对 B 只改变 RDE，匹配 Linux 的请求门控状态 |

这三臂是分解当前联合修改的最小阶梯；不需要改 S16、PGA、时钟、slot mask、CSR 或 PATH。A→B区分 RDL，B→C区分 RDE。若需要完整检验 RDE×RDL 交互，再补第四臂 `RDE=1 + 原RDL`，不应先扩大实验。

需要固定记录以下寄存器和判据：

1. `SAI_DMACR +0x24`：启动前完整32位值；B/C写后完整读回；退出时恢复原值并读回。B必须保持bit24=0，C必须为 `(old & ~(bit24|0x1f0000)) | bit24 | 0x0f0000`；所有臂bit8 TDE必须始终为0。
2. `SAI_XFER +0x10`：C中先确认 RDE/RDL 读回，再置 RXS bit3；退出先清 RDE并确认，再清RXS/等待idle/清RX逻辑。不要把“写函数返回0”替代寄存器读回。
3. 固定并读回 `RXCR +0x08=0x00400fff`、`FSCR +0x04=0x0101f03f`、`CKR +0x18=0x18`、内部回环活动期 `PATH_SEL +0x38`，以及8个 slot mask。三臂这些值必须相同，否则对照无效。
4. 每次 RXDR(+0x34) 前后记录 `RXFIFOLR +0x20`，至少保留前32词和完整256原始词；记录 `INTSR +0x2c` 的 RXOI(bit17)、采集耗时、stop/clear/restore结果。不得删零、压缩、重标采样率或把 bank0 子序列冒充16 kHz。
5. 判据：A与B相同而B与C稳定改变 bank level 消耗顺序或8词相位分布，才支持“RDE影响PIO观察行为”；三臂相同则该假设在此条件下不成立；A与B不同则 RDL 本身存在未文档化影响，当前联合实验不可解释；任何 RXOI、寄存器未恢复、停止失败、非同一时长/原始词数均使该轮无效。变化也不等于音频修复，后续仍需真实 DMA 或厂商 bank 规则佐证。

## RDE 启动前提

仅有 `CONFIG_DMA` 关闭不足以证明 DMAC0 不会响应 SAI1_RX 请求。现有 DTS/平台审查把 SAI1 RX 连接到 DMAC0 request 3；request 3不是硬件channel 3。C臂前必须确认当前非安全/安全 DMA owner、所有可见通道停止、无固件恢复通道的竞态，并在整个窗口保持独占。若无法证明，就只做A/B，保持RDE=0；这仍能安全地隔离RDL，不应为完成矩阵而盲开请求。

## 复核

`INPUTS.sha256` 冻结本次引用输入。运行：

```powershell
python work-in-progress/parallel-sai-rde-review-sol/test_analysis.py
```

脚本仅读取仓内证据，校验哈希，解码四个FIFO level字段并核对 Linux 配置语义；输出 `analysis-result.json`。它不访问 SDK、设备或网络。

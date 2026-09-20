# SAI1 离线配方候选，仍 NOT_READY

用户已明确确认 MIC 接了麦克风；本交付不再要求照片证明。仅本目录写入。没有访问 SDK、串口、I2C、USB 或板子，没有修改正式源码。A 负责 I2C3，B 负责 codec；本候选不复制它们的状态机。

`recipe.c/h` 是最小可核对的寄存器参数组件，不是 capture 驱动。使用原始 GPL-2.0-or-later `input/rockchip_sai.h`，候选同许可。固定 I2S、16kHz、双16bit、单lane、frame width ratio=1，输出5个 masked-update 描述；没有 MMIO 回调、start、stop、READY 或内存分配。函数成功仅表示配方算术成立。输出仍缺 role/polarity/path、时钟/复位/电源、DMA、codec 等设置，严禁直接按数组刷硬件。

## 源证据映射

以下源文件均逐字冻结到 `input/`，`inputs.json` 记录源路径和 SHA256。新补充 evidence 的 inputs.json 也冻结，保留原 Git OID 来源链。

| 事实 | 官方/项目源码依据 |
|---|---|
| SAI1 base 0x2a610000、size0x1000、SPI188，dmac0 tx2/rx3、PD_AUDIO、M/H resets | rk3576.dtsi:4454 |
| NuttX IRQ 编号=SPI+32，因此拟接220；实际handler/enable尚未接 | 项目 irq.h，usbhost.c:37的irq_attach错误检查示例 |
| SAI RXCR0x08、RXDR0x34、XFER.RXS bit3 | rockchip_sai.h 寄存器表与XFER宏 |
| 旧I2S_TDM RXCR0x04、RXDR0x28、RXS bit1，CSR也不同 | rockchip_i2s_tdm.h:58、228、308；旧寄存器序列不可复用 |
| I2S：VDJ_L、EDGE_SHIFT_1、RX_SHIFT_RIGHT(2)、FS双边沿 | rockchip_sai.c:431 fmt_create |
| S16、lane1、slot16、2slot、FW32/FPW16 | sai.c:536 hw_params；:994 set_tdm_slot；slot宽度不能从sample宽度自动推定 |
| DMA address RXDR、4字节bus、maxburst8、RDL16 | sai.c:1197–1215；hw_params maxburst=8*channels/2 |
| 内部源 mux/div：CLKSEL46 mux[10:8]/div[7:0]、gate8 bit4；最终mux46 bit11/gate8 bit5；HCLK gate8 bit6 | clk-rk3576.c:1416；父时钟audio_frac_int_p仍需实际选择与率核验 |
| clock IDs 76/77/78、MCLKOUT97，reset IDs133/134，PD_AUDIO10 | 冻结 dt-bindings；这些是框架ID，不能拿来当原始寄存器bit |
| 项目D-cache启用；USB用up_flush_dcache地址范围及dsb sy | defconfig:194/224、usbhost_xhci_rk3576.c:939等；不能等同已具备SAI DMA适配 |
| 项目MMU表映射DEVICE_REGION与若干独立外设 | rk3576_boot.c:61；需最终.config确认DEVICEIO范围是否覆盖SAI1、DMAC0、power相关地址，没有据此认定可直接访问 |

本范围未发现项目 SAI/DMAC0 capture provider。没有核对 SDK 全仓，不能声称不存在。Linux DMAengine API不可伪装成NuttX可调用API；尚缺目标DMAC0驱动、请求映射/安全域、描述符/地址宽度/中断及cache接口的目标头与实现。4字节FIFO总线宽不自行证明返回PCM已按2x16bit打包；需原DMA路径/硬件小样验证才能送已有PCM observer。

## 时钟与停止边界

配方只接受能精确整除512000的实际MCLK，MDIV范围1..4096；4.096MHz给div8、12.288MHz给div24。后者算术成立不代表codec在16k下可用。BCLK=16000*2*16。codec所需MCLK/fs、I2S主从/极性与板级MCLKOUT pinctrl仍应由A/B及集成方核对；配方不设置这些未知前提。

Linux stop先清DMACR.RDE，再清XFER.RXS，再poll idle/clear RX FIFO。版本<2307读XFER.RX_IDLE；>=2307读STATUS，>=2311还会调整idle bit。必须读取并识别实际VERSION，不能固定套bit。Linux clear轮询10us/最多1000us，超时会reset并返回0，xfer_stop也丢弃idle返回值：此处不能照抄为“真正停止成功”。reset先H域后M域，每段10us，尤其解决slave无输入CLK场景；但已知顺序并不提供本板reset寄存器控制实现。

后续真正stop至少要独立确认：关闭SAI请求；停止并确认DMAC0不再写入，屏蔽且排空在途回调；确认SAI idle与FIFO clear完成；按cache line独占缓冲区与实际cache API完成同步；最后才允许CPU读或释放。超时必须错误并保留DMA buffer所有权；不能只看到RDE=0/IRQ关闭就free。若采用整段录音，可固定最多3秒/192000字节，单owner，绝不因回调结束就推断DMA停止。当前组件不实施该数据路径，不保证真实录音时间界限。

## 复现与范围

在本目录执行 `python run.py`，20秒单进程超时。真实Windows MinGW GCC以C11、Wall/Wextra/Werror/pedantic编译并运行。`test-output.txt`保存原始命令/输出/exit，`outputs.json`记录交付哈希。测试检查独立常量期望值、所有输出不越mask、分频边界、非整除拒绝、无效输入不改输出。没有ARM64交叉编译或真实采样；未验证波形、左右声道、噪声、DMA、缓存、IRQ及停止。

暂不提供正式接入补丁：本组件作为可审查数值配方供真正provider引用；codec默认NOT_READY门禁保留。最小后续输入为DMAC0/IRQ/cache目标冻结接口与实现、最终MMU配置、SAI版本与时钟/复位控制实现、codec已核定16k序列。播放依旧另需功放及低音量门禁，本任务不启动播放。

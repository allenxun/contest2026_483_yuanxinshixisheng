# RK3576 原生 openvela NPU 适配与三功能融合

2026-09-07：用户明确调整顺序为先适配板载NPU，再融合仪器检测，之后增加语音交互。现有跟随和拍照基线保留，后续实验继续RAM启动。

最新实板进展：已新增原生 k7npu 诊断应用和受配置控制的 NPU MMIO 映射。固定 PMU/CRU 检查及两核心/四 MMU 只读探测通过，核心 ID 0x46495245、版本 0x00010002。低32位页表构建和 MMU 启停/恢复模块通过主机故障测试，并在真实 K7 连续两次完成四 MMU 的 0x18→0x19→0x18 状态变化及恢复，均返回 NSH。详细证据及当前镜像见 ../rk3576-npu/BRINGUP_PROGRESS.md。**尚未向 NPU 提交计算任务，不能宣称 NPU 模型推理或目标检测融合完成。**

新增可研究路径：固定版本的开放 RK3576 原始任务生成器在隔离 Ubuntu 主机上生成了 1×64×64 INT8 矩阵任务的143条指令。代码保留GPL许可证，未链接原生固件，未下发实板。此路径可用于最小任务验证，但不等价于已支持加载现有 .rknn 文件；完整模型运行时仍待实现。

后续进展：已实现单核一次性 rawtest，512KiB 私有映射、带符号非恒定样本/64个CPU标准答案、超时保留缓冲，主机测试与交叉编译通过。只有单独默认关闭开关控制的实验镜像链接GPL样本。该镜像 RAM 加载到61%时丢失U-Boot提示符，未启动，更未提交计算任务；CH340在线但K7不回应恢复命令，已请用户只复位K7，STM32保持不动。当前恢复状态见 ../rk3576-npu/RAW_MATRIX_TRIAL.md。不能把编译出的实验当成实板NPU计算通过。

## 当前核实结果

| 项目 | 证据与状态 |
| --- | --- |
| 当前系统 | native openvela/NuttX ARM64；不是K7 Linux用户进程 |
| CPU | 当前配置CONFIG_SMP_NCPUS=1；尚未八核调度 |
| 内存 | CONFIG_RAM_START=0x40400000、CONFIG_RAM_SIZE=132120576（126MiB）、MM_REGIONS=1；不是全部4GB物理DDR已可分配 |
| NPU BSP | 已添加 RK3576_NPU_DIAG 映射和 k7npu 原生诊断，实板可读两核心/四MMU；尚无模型推理后端 |
| 官方运行库 | RKNN Toolkit2支持RK3576；所核公开runtime目录为Linux/Android；没有在其中找到可直接链接本工程的NuttX运行库 |
| 官方内核驱动 | Linux RKNPU依赖DRM GEM或DMA heap等内存机制；直接复制源码不能完成NuttX驱动移植 |
| 模型准备 | 复用既有隔离RKNN-Toolkit2 2.3.2，新增仪器RK3576非量化候选；已有YuNet/FSA候选也未完成原生NPU板端验证 |

## 本轮完成的模型准备

源文件：交付包rk3568_reference/artifacts/onnx/device_yolox_s_v5_raw_opset12.onnx。该文件是可重新指定目标平台的ONNX，不是RK3568专用RKNN二进制。

- 源SHA256：30e1782cd50c1ebb9e760ebf033ad4126db0a1f21fa7f7a507b91bfc22357375。
- 显式target_platform=rk3576、do_quantization=False；没有使用测试图冒充INT8校准集。
- 候选：Ubuntu /home/swl/openvela/work/rk3576-fusion/npu-candidate/device_v5_rk3576_fp16.rknn。
- 候选22,381,341 bytes；SHA256 b3b433cba63598ecbce8be84f16da97c4d3a5ceb229356eac18441d5808168a9。
- 两组合成输入在PC模拟器与ONNX比较：三输出形状一致、数值有限；最大logit绝对差0.0240832，最小余弦相似度0.9999999507。仅数值烟测，无真实仪器识别精度或K7耗时证据。
- 报告device-rknn-report.json；可复现脚本prepare_device_rknn.py；原包及现用K7镜像未改。

输入是BGR uint8 NHWC 640x640，左上letterbox补114，归一化mean0/std1。输出是stride8/16/32原始logits，**不能直接使用PC整图模型已解码xywh的后处理**；需网格/stride/exp解码及objectness和class两次sigmoid，再做NMS。

## 实施顺序与通过条件

1. **先确定运行时可移植路径。** 核查RK3576可供移植的模型加载、任务生成、内存与提交接口。当前Linux librknnrt.so不与本项目aarch64-none-elf/NuttX ABI直接兼容。需要可移植源码/RTOS库或充分任务接口资料；仅有寄存器地址、ONNX转换成功或Linux演示均不代表这一层解决。没有证据前不承诺纯openvela NPU完成日期。
2. **补充BSP资源与内存契约。** 从实际K7 DTB及官方资料确定NPU电源域、稳压供电、SCMI/CRU时钟、复位、两路中断、IOMMU、DMA缓冲与cache同步。DDR扩容先查保留内存与地址洞，不能直接把RAM_SIZE改成4GB。SMP独立验证PSCI启动/核拓扑/中断与调度；它有助CPU任务隔离，但不是NPU启动的必然前置条件。
3. **最小NPU任务实板验证。** 合法缓冲分配/地址转换，执行小模型，收到中断并核对结果；覆盖超时、故障清理和重复运行。需要真实硬件结果与耗时，不以模拟器代替。
4. **仪器模型单独验收。** 候选版本与实际runtime/driver配对；真实仪器图对拍、raw输出后处理、检测精度、内存峰值和推理时间。FP16先正确，获得合适校准集后再评估INT8。
5. **三功能融合。** 人脸更新/跟随优先，仪器检测取最新帧、最多一个待处理请求、有截止时间和过期结果丢弃；姿态仅对当前主脸ROI。云台唯一UART出口不变，目标检测不改舵机目标，照片单独固定同帧并确认落盘。NPU作业按实际可用调度能力排队，不默认多个模型可同时占满硬件。
6. **再接语音。** 先验证麦克风与播放的驱动、DMA和连续音频缓冲，再接唤醒/ASR/意图/TTS。具体模型逐项验证NPU算子及内存，不能保证任意语音或大语言模型都能上NPU。音频采集与云台控制有固定服务预算，视觉和语音推理不得无限排队。

6 TOPS属于硬件规格，不能直接换算当前FP16模型端到端帧率。应同时记录视频帧率、检测周期、目标年龄、CPU/NPU耗时、跟随响应、音频丢块和内存峰值。

## 官方依据

- RKNN工具链与RK3576支持：https://github.com/airockchip/rknn-toolkit2/blob/master/README.md
- 公开运行库平台：https://github.com/airockchip/rknn-toolkit2/tree/master/rknpu2/runtime
- Linux驱动内存依赖：https://github.com/rockchip-linux/kernel/blob/develop-6.1/drivers/rknpu/Kconfig
- 芯片设备树资源：https://github.com/rockchip-linux/kernel/blob/develop-6.1/arch/arm64/boot/dts/rockchip/rk3576.dtsi

以上为2026-09-07读取的公开分支资料，正式实现需固定源版本并与K7 SDK核对。

## 可向KICKPI/瑞芯微工程师询问的具体资料（尚未发送）

“我们已将openvela/NuttX原生移植到K7 RK3576，使用AArch64 ELF平坦构建，计划原生驱动NPU。请确认是否提供RK3576 NPU的RTOS/NuttX运行库、可移植runtime源码或模型任务生成/提交接口；现有librknnrt仅见Linux/Android版本。另请提供对应版本NPU寄存器/任务描述、内存与IOMMU要求、SCMI/电源/复位依赖及可运行的小模型样例。我们需要原生RTOS执行资料，Linux演示仅可作硬件对照。”

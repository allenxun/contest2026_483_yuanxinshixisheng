# 原生 ASR decoder Session 验证

此目录是主线语音配网的独立诊断候选，不是可用的语音配网程序。

2026-09-11：模型探针及 SHA256 实现已通过 ARM64 编译，与锁定的真实 ASR/TTS 运行库完成可重定位链接。链接对象 SHA256 为 `9b55425f596a21274debcf2b094b9d7943a7edfe88637b3ab822cc25cf8fbb88`。原始命令和输入哈希见 `link-result.json`。首次 SHA 编译缺少 vendor include 路径，补齐路径后通过；没有改变 SHA 算法。

独立固件构建目录为 Ubuntu `/home/swl/openvela/cmake_out/velavision_voice_asr_model_20260911`。新增 `k7voice asr-model` 仅在显式编译选项打开时可用。正式两个入口文件及 SDK 对应文件均按修改前快照核对，记录在 `sdk-entry-change.json`。本轮没有同步无关的解析器改动。

## 真机前置条件

- 尚未上板，尚未运行真实 decoder，不能宣称语音识别或配网成功。
- decoder ORT 文件大小 72,024,848 字节，完整 SHA256 见 `inputs.json` 与 `model_lock.h`。
- OTG 暂存地址为 `0x80000000`。只有完整模型校验后才能调用命令。此地址属于 CPU 模型池，不是存储分区。
- SDK `mm_initialize.c` 的 `mm_addregion` 仅在 `CONFIG_MM_FILL_ALLOCATIONS` 打开时填满区域；候选禁止该选项和 KASAN，最终镜像仍须核对实际配置。堆首尾元数据与模型暂存区不重叠。
- 先核对源 SHA256，再初始化模型池；申请独立持久缓冲区后检查其结束地址不超过暂存地址，再复制并核对目的 SHA256。后续 ORT 分配可以覆盖原暂存区，不再读取原暂存区。
- Session 显式顺序执行，线程数为 1；模型池配额 768 MiB。普通 C++ 元数据仍可能使用系统堆，需要真机观察其峰值与失败行为。
- 此探针只验模型 Session 创建与释放；没有音频输入和推理输出。必须后续验证 encoder、真实 WAV、麦克风与配网状态机。

## 复现

Ubuntu 候选目录中执行 `python3 build_probe.py`。该脚本复用已记录编译参数并核对运行库哈希，完成的链接对象禁止覆盖。`build_firmware.py` 核对修改前入口后创建独立构建目录，同样拒绝覆盖已有目录；不操作板子或刷写。

独立固件已完成1655步构建并最终链接通过，镜像SHA256 `c8f58b202842032ea155d877fb91003df70c2480039b93851a2e10c98c9da9ca`。构建原始输出见 `../../evidence/build/voice-asr-model-20260911/`。尚未上板。

真机进展：decoder OTG传输72024848字节耗时7.753秒，源RAM与0x80000000目标CRC均为2af64aa7，通过。再次进入Fastboot后Windows/Ubuntu均未枚举到OTG，尚未下载新固件；当前板子停在U-Boot下载模式，Wi-Fi/BLE不在线。用户已被请求仅重连OTG线。准备了88802064字节的单次模型+固件包，尚未使用或真机验证。

本轮已恢复OTG并完成模型+固件单次传输：88802064字节、9.8077秒，整包及两段目标CRC通过，voice-asr-model-20260911 RAM启动成功。真实模型源与复制目的SHA通过，Session创建失败：Deserialize tensor /decoder/decoders.15/norm1/Constant_1_output_0 failed；分配器peak=73074640、live=0、failures=1。不能称ASR成功。首轮源码保存在model_session-attempt1.cpp和shared_runtime-attempt1.hpp。下一候选把有界记录数128调整为2048并增加peak_count输出，尚未编译/上板；记录数上限目前只是待验证原因。

第二轮 attempt2：分配记录上限2048，内存配额仍768MiB，增加失败原因和失败请求大小。ARM64编译、链接、1655步独立固件构建及ELF审计通过；固件00aa03c4294d2c801c465c9ca12c5838c5efe73e755285bf826e3e70f5396fc0，当前待VMware连接OTG，尚未上板。主工具tools/audit_arm64_unwind.py优化符号名读取，与第一轮缓存审计全部字段一致，保留同样的静态验证边界。

# RXDR 暂停取数诊断

在通过两次独立 ASR 的 voice-tls 基础上，仅新增 `k7sound capture-pause250`。不改变 CSR、时钟、DMA 或默认录音路径。固定采集 128 对字，前 8 对后暂停 RXDR 读取 250 微秒，只读中断状态和 FIFO 数量；然后用既有固定 32 条 trace 记录恢复取数后的数据。观察是否在没有 CPU 读取时已有多个 FIFO 积累。

暂停最多 100000 次循环；时间回退、超时、RX 溢出均失败并执行既有停止/恢复路径。调度延迟导致暂停达到 1 毫秒也拒绝。诊断结果不允许 replay 或传给 ASR，不能当作正常采样修复。

输入快照在 input/，哈希同步基线在 evidence/sync/audio-pause-baseline.json。O0/O2 主机测试包含原 PIO 回归，以及暂停间隔、暂停中溢出、时钟冻结退出。最初模拟溢出位写错两次，失败输出已保留；按输入官方头文件 RXOI bit17 修正后通过，未更改设备溢出判断。

复现：在 E:/openvela 执行 `python VelaVision/work-in-progress/audio-pause-20260911/test.py`，依赖既有 MinGW 路径。build.py 仅供 Ubuntu SDK，使用已验收 TLS runtime.o 的固定 SHA256，创建独立构建目录。主机通过不等于真机结论。

本轮不写 eMMC/STM32，不启动执行机构。真机结果待加载后记录。

构建已通过：BIN d802b88da7c984ea4e69b05d2f9a37c6bb22cd9441100aaa100ee586e7a81582，内存末端0x41721000，DTB及原系统RAM界限未触及。等待VMware连接OTG；未进行真机暂停诊断。

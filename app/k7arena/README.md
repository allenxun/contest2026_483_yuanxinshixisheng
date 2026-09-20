# 显式模型池 ggml 诊断

入口 k7arena，独占模型池、最多1MiB，正常两个64x64张量共32KiB。8192项set/get及范围/归还检查；不计算图，不加载权重。
仅CMake接入，复用k7graph的固定b5046实现，不重复编译BSP arena。未编入host-mock/KAP_HOST_MAIN/K7_BUFT_TESTING。模型池/普通堆的失败、隔离和生命周期边界以来源候选HANDOFF为准。
来源哈希见evidence/arena-provider-20260910/integration.json；单次正常通过不等于OOM/全DDR/模型验收。

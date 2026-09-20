# 真实 CPU 张量图诊断

固定b5046 ggml、checked线程池、graph-probe-v1。入口k7graph both，2/4软件线程，64x64逐元素乘法，4096项独立校验；不加载权重，不是矩阵乘法或token推理。
此版本只接入CMake构建。默认未绑核，不能说已利用四颗A72。底层compute/join可能阻塞，主会话外部监督；不强杀后释放仍被线程使用的内存。上游部分OOM仍abort。
来源与文件哈希在evidence/graph-core-20260910/integration.json，许可证vendor/LICENSE。原始vendor冻结不改，局部UNUSED宏仅作命名空间派生。

# SAI RX DMA-request gate 单变量实验

S16 真机配置正确进入 `RXCR=00400def`、`FSCR=0100f01f`、`CKR=38`，但仍以固定四词周期取得一个有效词和三个空词，并在 3200 帧请求上以 2399 帧超时。因此槽宽不是周期零样本的根因。

本实验回到已能完整采集的 S32 路径，仅在 RX 运行期间匹配 Rockchip Linux 驱动的控制顺序，设置 `DMACR.RDL=16` 和 `RDE=1`，随后在停止流前恢复原 DMACR。CPU 仍直接读取 RXDR，没有配置 DMA 控制器，也不把该试验称为 DMA 传输。

目标是确认 RDE 门控是否改变 CPU 读取 RXDR 时的四 FIFO 选择。现有采集、S16、喇叭、无线、模型和 TLS 路径均保持不变。

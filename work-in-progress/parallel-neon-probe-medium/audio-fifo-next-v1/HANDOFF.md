# 下一单变量：仅 RX 从1并行lane改为2

candidate/duplex.c/h与最小rx-csr2.patch已完成，O0/O2实际主机测试通过。独立显式入口：

```c
dl_run_numbered_rx2(&port, 1, common_verified, 4096000,
                    capture, 512, &result);
```

仍静音内部loop0、固定128个接收word-pair、默认PATH4e4e4、同编号TX源。只将RXCR.CSR[21:20]编码0→1，即1lane→2lane，RXCR00400fff→00500fff；TXCR仍00400fff。SNB2、slot32、FS64、CKR18、RX_SHIFT2、DMA0、原计数/终止/功放/路径恢复均不改。不组合RXALL或MMU试验。

## 选择依据和预测

TRM SAI-layout.txt 的RXCR CSR字段明确0/1/2/3为1/2/3/4个并行channel；SNB是每frame slot数。官方rockchip_sai.c rockchip_sai_lanes_auto（524）及hw_params（587–620）分别设置CSR(lanes)、SNB(channels/lanes)，FS宽度由slot_width*ch_per_lane计算。因此2lane×2slot保持64bit FS是可核对的配置；不把SNB改1同时保留64bit FS当成可靠单变量。修改TX并行lane会提高发送消耗，可能触发原总入队上限，故本次先改RX。

按文档的并行slot数推导，每个16kHz LRCK周期应从2word变4word；收满128个word-pair（256word）预期从约8ms缩为约4ms，加同等启动延迟。这个时长预测只适用于硬件按并行lane语义交付PIO条目；不是已证实行为。若时长缩短并出现额外条目，支持CSR控制当前接收吞吐；若仍约8ms且编号/银行模式完全不变，则当前PIO bank统计与文档通道预期仍不符。若溢出、错误或超时，不能作为映射结论。

新增lane1仍为默认RX path1→SDI1，没有打开loop1或修改引脚。它可能没有有效外部源；保留其所有原值，不声称它应为零或有意义。主要判据是有效FIFO条目产生速率、编号的原始分布和采集时长，不要求声音改善。不把银行编号直接当lane编号。

已编号真实输出证明62个不同序号推进且只有8k+6/7被看见，因此固定陈旧marker假设不成立。它仍可能体现TX、RX或PIO内部选择。MMU尚未以本任务证据证明运行期通过，不能排除或先验归因。

## 恢复与输出

新模式在改配置前记录rxcr_before，配置后记录rxcr_active，并用实际RX值执行原expect检查。只在原stop成功后恢复此前CSR位（不是覆盖整个RXCR），读回rxcr_restored，新增rx_restore_rc。任意CSR恢复失败使最终非0且held=1；stop失败不写CSR恢复。PATH恢复仍保留并独立检查。默认三个旧入口沿用rx_lanes=1，不增加CSR恢复行为。

root需打印rxcr_before/active/restored与rx_restore_rc，保留start_us/end_us、每银行FIFO轨迹、全256word。此模式result.frames仍是原代码的word-pair计数，**不能将128直接解释为128个16kHz双声道音频帧**，不能导出WAV或接ASR来评价采样修复。只有在独立解释好lane布局后才能定义声道格式。

## 测试与追溯

inputs.json固定7项：正式duplex.c/h、真实SAI头、编号raw/analysis、TRM、官方Linux驱动。build.py生成候选与差异，gcc C11/-Wall/-Wextra/-Werror O0/O2真实执行；命令/返回值runs.json、原始compile/test-O*.txt。

测试继承全部默认/路由/编号/停止失败用例；新增模拟2lane每LRCK4word、额外lane零原样保存、TX/FS保持、旧非零CSR位恢复、CSR读回错拒绝、恢复失败held、stop失败禁止恢复。该模拟器刻意采用上述文档假设测试软件能处理更高条目率，不能证明真实SAI按该模型工作。不修改正式/SDK、未交叉编译或设备操作。封存后不改本目录文件。

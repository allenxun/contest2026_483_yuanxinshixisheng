# 主机复核结果

- 时间：2026-09-11（Asia/Shanghai）
- 命令：`python work-in-progress/parallel-sai-rde-review-sol/test_analysis.py`
- 退出码：0
- 结果：12项冻结输入哈希全部匹配；`0x00082082` 解码为四FIFO各2项；早期RX trace前八次level/word序列匹配；内部回环周期零样本状态匹配；Linux参考中的RDL16、RDE启停、RXDR 4字节bus与RDL的N-1编码均匹配。
- 边界：S16目录在复核时没有 `board-result.json` 或原始真机日志，脚本明确输出 `board_result_present=false`、`raw_runtime_logs=[]`。主机测试不替代真机验证。

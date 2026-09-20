# Marker decoder v2

实测指定原始audio-route日志含171个CRLF、0个CRCRLF；冻结v1能直接从该raw解析256字。因此没有把本条真实日志误判为双CR。但对同内容显式转换的CRCRLF输入，冻结v1确实拒绝；v2已补齐。

新decode.py只将文本行终止符CRCRLF、CRLF规范化为LF，再逐行严格校验LOOP_PCM。每行必须8个完整8位hex word、偏移连续、总共256字；截断、重复/跳跃偏移、半字均拒绝。标记encode/decode和report不改，零值不会被过滤。

input保留原始raw bytes和旧decode.py，inputs.json有来源SHA。raw SHA256=4c56ecaf2fc4f4b11e4ed695cc0229da4c56efc92fddf92a485d129df00eea19。实际主机test.py通过LF/CRLF/CRCRLF完整输入及每种5项错误输入；均得到256字/194零，与原始word数组完全相同。原输出test.stdout.txt，结构化results.json。测试旧固定标记仅针对parse，不冒充编号marker解码成功。

复现：`python prepare.py`，`python test.py`。使用：`python decode.py raw-log.bin`，JSON输出stdout。没有改冻结v1、正式源码、原始证据或设备。本轮测试脚本初稿修正了多余括号以及误把TX trace词截断当PCM截断的测试构造问题；最终失败用例明确修改LOOP_PCM行。

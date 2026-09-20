# RX2 guarded 独立入口

候选candidate/duplex.c/h + candidate/rx2_ready.c；rx2-guard.patch包含两个现有文件差异和新增helper。root需把rx2_ready.c加入k7sound编译。原正式源码固定input/及inputs.json，旧封存目录不动。

```c
dl_run_numbered_rx2_guard(&port, 1, common_verified, 4096000,
                          capture, 512, &result);
```

固定128个接收word-pair，只允许原编号RX2/default route组合。新入口在RXFIFOLR原始值转总数之前使用已封存rx2_pair_ready：bank0>=2且bank1>=2才读pair；任一bank2/3非零或bank0/1深度>32立即-71，不自动回退。保留所有RXDR结果，完全不按值删除零。

其余旧入口guarded=0，使用原sum>=2判据；不改CSR、TX marker、TX refill、deadline、time budget、功放、stop、PATH/CSR恢复。旧raw baseline仍能复测。guarded失败继续原cleanup，stop/restore错误保持held，无吞错或新reset。

主机O0/O2严格C11/-Wall/-Wextra/-Werror全部通过。mock明确模拟每次先向两个bank各加1，再积累到各2：验证第一次(1,1)没有RXDR，第一次真正读取前raw=82(2,2)，256原字完整保留。未知bank、非法深度均在RXDR前拒绝并正常恢复；永远停在各1触发原deadline且零次RXDR；同时clear卡住保留held。旧默认/编号/RXALL/RX2及原失败测试继续通过。测试模拟不证明硬件bank cursor，实际效果仍需原始trace判读。

原命令/返回值runs.json，原始compile/test-O*.txt；build.py可复现候选和补丁。未交叉编译/未操作SDK或设备，未改正式代码。本方案只诊断pair启动完整性，不把稳定bank1零当空读，不宣称已修复音频采样。

# Guarded RX2 的 path1 同源候选

候选已完成但**等待guard真机结果后再决定采用**。只修改自己目录，未操作SDK/设备或正式源码。

新显式入口：

```c
dl_run_numbered_rx2_guard_same(&port, 1, common_verified, 4096000,
                               capture, 512, &result);
```

基于当前guard正式快照，仍固定128word-pair、RXCSR2、编号TX、两bank各>=2门限、功放低。唯一增加的硬件配置变化：PATH_RX1[11:10]由1(SDI1)改0(SDI0)，与path0同源。默认active4e4e4变4e0e4，其余RX path2/3、TX route e4、loop0、时钟、SNB和slot不变。没有开启loop1或改引脚。

TRM SAI-layout.txt 823–828行字段名rx_path_select1、位[11:10]与reset1明确；其描述正文误重复Path0名称，官方SAI_RX_PATH_SHIFT(1)=10及MASK(1)=3<<10独立支持字段位置。原RX_ALL使用全部[15:8]，本候选仅将现有保存/恢复mask增加SAI_RX_PATH_MASK(1)，因此既有完整active读回与masked恢复读回自动覆盖新增位。旧入口same_input=0，无行为改变。

预测：若稳定零来自RX path1选择的额外SDI1源，改为SDI0后应在相应银行看到同源编号，可能形成同一对编号重复到两个lane；不要先验固定pipeline延迟或跳过启动零。若仍同样零，当前lane/path/PIO的关系仍未解释，不能强行删零。即使同源回环完整也只是两个并行lane同源的数据路径证据，不是普通双声道采样已修复。

交付candidate/duplex.c/h、原样rx2_ready.c和rx2-same-input.patch。正式已有helper，无需新增第二实现，只复用现有rx2_ready编译项。所有前置、deadline、stop/CSR恢复/held处理保留。唯一新API无可组合RXALL参数。

build.py冻结5项来源/哈希到inputs.json，生成候选及补丁。O0/O2 gcc C11/-Wall/-Wextra/-Werror实际全通过；原命令/返回值runs.json、原始compile/test-O*.txt。新增mock验证PATH4e0e4、原非零path1恢复为e4e4、path1专属读回错误启动前拒绝、恢复时丢bit10可检出并held、写恢复失败held，以及TX/FS/RXCSR不变。原guard/非guard/编号/RXALL测试保留。

模拟器在选择SDI0时把同一字送入两个队列，这只是验证软件处理与恢复，不是硬件测量；真实复制顺序与零位置待采集。未交叉编译，未宣称修复，不更新任何旧封存清单。

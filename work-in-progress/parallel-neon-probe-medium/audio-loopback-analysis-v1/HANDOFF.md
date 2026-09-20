# 内部回环分析及 RX 路由单变量候选

**可集成候选**：candidate/duplex.c/h，最小差异rx-all-route.patch。默认dl_run保持原路由与接口。新增显式调用：

```c
dl_run_route(&port, 1, common_verified, 4096000,
             capture, 512, 128, DL_ROUTE_RX_ALL_SDI0, &result);
```

只新增RX_ALL模式，并限定128frame；默认模式仍原8..256frame。该模式PATH RX路由[15:8]全清0，四path都选择SDI0；TX低字节保持e4，loop0保持bit18=1，active从4e4e4变400e4。恢复mask同时从fc0303扩大到fcff03并读回，保留非零原RX路由。没有改CSR、slot、clock、DMA、marker、amp、poll、终止/清理逻辑。没有集成MMU变量。

输入原样冻结与SHA在inputs.json。analyze.py实际复核256原字、前64TX/RX轨迹：前8字0，之后31次重复 `0707ef00 08081100 0 0 0 0 0 0`。每声道非零相位[31,0,0,0]。预填16字逐写银行增量完全符合每2字bank0→1→2→3轮转，最后四银行各4entry。结果与原始数据见results.json/test.stdout.txt。

## 解释边界

内部loop0重现三零相位，因此codec ADC、MIC、外部SDI输入不是出现该模式的必要条件；但不能因此定为纯RX问题。TX银行0预填marker1/2、银行1=3/4、银行2=5/6、银行3=7/8，而稳定RX银行0收到7/8：银行编号与串行path的直接等同假设不成立，存在尚未解释的TX串行选择/时序或PIO银行序列。固定重复marker不能证明输出7/8每轮都是新鲜读取，也可能无法区分延迟/锁存。FIFO entry计数并非样本有效性标签。

TRM page934 PATH[15:8]四个2bit选择器定义RX path0..3取SDI0..3；官方rockchip_sai.h SAI_RX_PATH_SHIFT/MASK、Linux mixer rpath枚举一致。当前CSR0仅声明单并行通道，不能因为四银行轮转自行推断4个串行lane已开启。官方求和FIFO实现支持保留四银行计数，但未解释CPU轮转与lane映射。没有文档依据直接启DMA修复。

## 最多两个后续实验

1. **本候选RX四path都接SDI0**：一次128frame，amp强制低、同marker/预填、同stop/restore，与旧回环只差RX路由位。若原零相位变成标记（尤其相同7/8进入其他银行），支持多个RX path的数据选择参与当前轮转，反对“仅有效lane0加不可改变零填充”的简单模型。若原样不变，只说明这些选择位在当前配置未改变观察；不能由此证明单lane硬件正常或直接宣告PIO损坏。若顺序/相位改变但不完整，报告原始序列，不删零。任何overflow/timeout/restore失败不作格式结论。
2. **以后单独的带循环编号marker**：仅软件源序列给每个8字周期增加不重叠的周期字段，保留8字位置标签。若RX7/8位置随周期推进且延迟稳定，支持实时选择某个入队相位；若长期停在同一周期，支持锁存/陈旧输出。它不能单独定位TX/RX银行根因。本轮不实现或合并此变量，先运行实验1。

## 主机验证

build_route_candidate.py从冻结正式duplex生成candidate与patch，gcc C11/-Wall/-Wextra/-Werror，O0/O2实际通过，命令/返回值runs.json、原始compile/test-O*.txt。复用完整duplex失败测试；新增RX_ALL读回400e4、非零旧路由e4e4/b4e4恢复、TX e4保持、PATH读回错、恢复失败held、128frame硬上限及非法mode拒绝。模拟器不声称验证真实银行模式；未交叉编译、未操作设备。

接入者仍须确认prepare/muted、共享主时钟及amp_low回调。本组件不新增codec或功放enable回调。失败held边界不变，旧源码与输入清单保留。

# 单变量编号标记候选

candidate/duplex.c/h 基于当前正式路由版本冻结生成；最小差异numbered-marker.patch。旧dl_run和dl_run_route保持原标记与接口。新显式入口固定128frame，不能指定RXALL：

```c
dl_run_numbered(&port, 1, common_verified, 4096000,
                capture, 512, &result);
```

要求原RX路由[15:8]=e4，否则无寄存器写入且held拒绝；正常PATH仍4e4e4并恢复e4e4。只变发送标记源，CSR/slot/DMA/clock/TX路由/功放/stop/恢复/trace都不改。新入口没有功放enable或codec hook，继续amp_low强制低。

## 编号约定

`n`为从0开始的**入队word序号**，不是帧号或银行编号。旧runner入队总上限2*(128+16)=288，因此本实验n=0..287，cycle=n/8、position=n%8。

`word = 0x01000000 | (position << 20) | ((cycle+1) << 8)`。

低8位恒0；所有标记非零、正数、幅值小于2^25；position占22:20，cycle+1占19:8，高位固定签名。cycle+1避免首周期变零。导出函数dl_numbered_marker支持主机逐项验证，n>=288或空输出拒绝。内部生成依赖原enqueue硬上限与固定128帧，不在失败路径补零。

例：n0=01000100，n1=01100100，n6=01600100，n7=01700100，n14=01600200，n15=01700200。原先重复7/8的现象，若转为01600100/01700100、01600200/01700200等可证明看到不同入队周期；若始终同两编号则支持陈旧/锁存模型。仍不能仅凭编号定位TX或RX内部银行。

## 反解

`python decode.py 原始log.bin` 输出JSON到stdout，程序不写音频。输入限2MiB、严格连续LOOP_PCM偏移及256word；拒绝截断、重复dump。每字保留raw/RX序号/帧/声道，零值明确标zero；非零先校验签名、低位及范围，未知格式标invalid而不猜序号。合法字给enqueue_word/cycle/position及RX序号差，后者**不等于已证明的物理延迟**。有tx_queued时检查反解序号在已入队范围内；前64条TX trace对照编码器校验。

不要把decode成功、transfer0或编号推进当音频采样修复。本实验仍保留全部三零相位，不重采样/删除零。首窗pipeline对齐由实际trace判断，不预设首个有效周期一定为0。

## 验证与证据

inputs.json冻结正式duplex.c/h、实际SAI头与本次两个真实路由日志。脚本核对RXALL和同镜像默认原数据完全相等：8零后31组旧7/8+6零。该结果关闭“仅把RX所有path映射SDI0即可消零”的简单假设，不能证明更广泛路由语义正常。

build.py生成patch和candidate，gcc C11/-Wall/-Wextra/-Werror的O0/O2实际通过，保留compile/test-O*.txt、runs.json。覆盖旧默认与RXALL行为、全部288字唯一/反解、128frame新模式入队和捕获逐字相等、默认路由拒绝、stop/restore失败held。test_decode.py覆盖288往返、无效字、194原零保留、合成编号推进62个唯一序号与旧编号重复2个、截断/重复输入拒绝；原输出decode-test.stdout.txt，结构化decode-test-results.json。

未交叉编译、未操作设备；没有真实编号marker采集结果。root独立集成此源变量，暂不同时改MMU/RX路由或其它参数。封存outputs.json之后不再改本交付。

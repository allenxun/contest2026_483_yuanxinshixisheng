# Root live integration review

仅审查inputs.json绑定的正式源码快照；不重复构建/测试，无设备操作。以下是当前快照需修的准备/恢复问题，不是已观察到硬件故障。

1. k7audiohw_main.c:88–106 在读I2C/GPIO之前只检查GATE11 PCLK_ROOT，没有检查当前CLKSEL55父项及其GATE0门。开子门并不能恢复上游被关的PCLK。必须当次解码SEL55[3:2]：0需要GATE0bit1开、1需要bit0开、2是xin24m、3拒绝未知；与root其余输入链/电源证据一起决定能否读外设。冻结preflight父门为开，但不能把前一镜像采集作为新镜像永远成立的条件。还应在首次外设读前检查子门写回匹配，而非等切mux后再验I2C门；GPIO门目前根本没有读回检查。

2. :123–140 restore无冲突检查、无恢复读回，任何写失败仍返回0。特别prepare :115检查source/gate/mux失败后即进入此恢复路径，不能继续盲写并称restore=0。建议分阶段记录已完成字段和预期值，进入恢复前核对自身字段、IEN/EN与controller ownership；冲突或不能确认PCLK访问条件就拒绝。恢复CON tuning/CLKDIV/CON1后先读回匹配，再恢复mux/source/gates并逐项比较；失败返回非零、锁存故障，保留未完成项。当前bus.active/held仅覆盖live事务，不能代替prepare阶段和其他写者的真实状态。

CON1本身的版本>=5保存及同条件恢复是匹配的，没有发现漏保存/错误偏移；主要缺口是它和CLKDIV一样缺恢复读回。原CON恢复仅tuning是明确禁用控制器的状态，不应称“全CON逐位原样恢复”。源切换及逆向恢复前先关功能门，PCLK保持至控制器恢复后，这个顺序正确。SRST_GPIO4 293/294=>SOFTRST18 bits5/6，现有a48&0x60检查正确；I2C SPI91=>INTID123一致。

GPIO采样从v2 EXT_PORT读bits12/13而非DR输出锁存，这一点正确。lines()两次高值间隔5us只证明两个采样点为高，不证明间隔内绝无低脉冲；在独占/控制器静止的假设下可作有限idle判据，日志不要称电气连续测量。代码本身没有建立/读证IO输入缓冲状态，因此不能从GPIO版本号推出mux11采样必然有效；这属于仍需root板级证据的前置条件，未从现有源码确认某个必须写的输入使能寄存器，不建议猜地址增加写操作。

STOP失败时live保留held/active，restore拒绝更改硬件，这是符合方案的失败关闭。当前main无显式cleanup重试命令，后续重入会fault_latched；若实板触发此路径，需要root外部监督执行明确恢复或重启，不能报告已清理。clock_gettime返回值未检查也是边界弱点（失败会使用未初始化timespec），建议作为小修补检查，不是当前已证明的正常探针阻断原因。

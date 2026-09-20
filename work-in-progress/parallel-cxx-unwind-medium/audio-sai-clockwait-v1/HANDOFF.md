# Explicit opt-in 20us clock wait

新增pio_run_clockwait，签名与pio_run一致；port结构、既有公开API签名不变。内部run增加私有clockwait参数，旧pio_run和pio_play_buffer均传0，新入口传1。仅新路径在DIV配置之后、CLK/FS enable紧前显式等待至少20us，不增加reset、clear或改动FIFO。官方冻结rockchip_sai.c:654–679 prepare主模式在DIV后udelay20再CLK/FSS enable，理由为一个BCLK周期稳定；这里只移植该有界等待。

clockwait20使用已有us回调；每次检查时间倒退返回-5，至多100000轮，时间不走返回-110。等待失败走原有done清理而不启CLK/FS；不将失败吞掉，也不重置硬件。计时回调应使用root已验证硬件counter换算，不要使用毫秒tick实现微秒等待。长抢占导致实际等待>20us符合“至少20us”而非精确20us承诺。

test.c直接编译candidate pio.c，严格C11 O0/O2均通过：20us门槛、冻结时钟次数界、倒退、全新路径DIV至enable观测21us、旧路径无额外等待、两次RX真实数据和frames保持一致、冻结时钟未启CLKFS/未读FIFO数据。run-evidence.json保留最终原始命令及输出。首轮test.c因一行if/return缩进被-Werror拒绝，已修测试格式后重跑，不是产品代码错误。

inputs.json固定修改前正式rxtrace pio.c/h和精确官方依据。root正在添加reset/start-clear，故**不要用本目录整份pio.c覆盖新正式文件**：clockwait.patch是冻结基准最小差异，应在当前集成中仅合入helper、私有参数、等待点及新wrapper，并保留其它新入口各自参数。root使用新入口做独立clockwait控制模式；既有调用行为保留。未操作设备/SDK/正式源码，未声称等待能够修复真实RX样本周期问题。

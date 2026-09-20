# I2C3 timing pure-function candidate

交付i2c3_timing.c/h：输入明确的功能时钟Hz、目标SCL Hz、SCL上升/下降ns和inputs_known，输出CLKDIV低/高16位及CON tuning字段。无MMIO、无时钟探测、无默认晶振、无分配。为首阶段限定Standard-mode 1000..100000Hz，不扩展到Fast/Fast-plus。实际输入时钟、边沿依据和目标速率均由主会话提供；inputs_known=false返回-EAGAIN，输出不修改。

来源为官方冻结i2c-rk3x.c的rk3x_i2c_v1_calc_timings（约871–1006行），文件SHA256 67b6eb49cdb0838bcd00e58021847461fe4b7fa4142f15f3de3ac59ac9b17bb5；已原样保存i2c-rk3x.frozen.c。DTS兼容链包含rk3399-i2c，其soc_data选择v1算法；不按函数名v1误判为芯片硬件version=1。真实控制器版本与适用配置仍待集成核对。

保留官方kHz取整、低/高周期比例分配及SDA/start/stop tuning选择；使用uint64算术，最终提交前校验寄存器范围和精确Hz公式。相较官方行为，本候选不静默夹紧非法速率、不返回截断的最佳努力divider，不接受SDA无有效选择时回退为1，也不截断超过支持范围的start/stop值。先判断再做无符号减法，避免低输入时钟下setup计算下溢。所有失败保留调用者原输出，只有全部条件满足才写结果。

纯函数校验低/高周期（含所给SCL下降/上升时间）、SDA hold/setup、START setup/hold、STOP setup与实际SCL不超过请求。它不是整个I2C bus时序控制器：调用间bus-free、实际rise/fall、上拉/负载、STOP与线路idle、时钟来源稳定性和分频寄存器写入同步需下层另证。没有将计算结果直接变成codec clock_ready或允许硬件访问。

## 主机结果

运行 `python -B verify.py`，C11 -Wall -Wextra -Werror -pedantic，O0/O2均通过7个显式边界+160组时钟/速率/边沿组合。96组接受、64组-ERANGE；接受结果逐项与从冻结源码提取的官方函数比较div_low/div_high/tuning一致。oracle将unsigned long映射uint64_t以模拟AArch64 LP64，避免Windows LLP64差异；仅在本候选接受的受限输入比较，不拿官方低值下溢行为作应当接受的依据。test.c中的边沿与频率全部合成，无目标时钟读取。

合成例：输入24000000Hz、目标100000Hz、rise/fall各100ns，得div_low=16、div_high=12、CLKDIV=0x000c0010、tuning=0x00001200、SCL上限100000Hz。这不是板端读数，不建议未核验时直接写这些值。极低时钟、零/未知时钟、越界速率、超大输入与divider范围失败均保持输出不变。

原始命令/输出和依赖哈希见run-evidence.json；完整交付哈希见delivery.json。候选基于GPL-2.0-only官方函数，保留许可证与原作者归属，未标成Apache来源。该许可证信息是源码追溯的一部分，不表示已经并入正式工程。

## 待完成项

主会话只读确认I2C3实际parent/mux与输入Hz，提供可靠的板端边沿/电气约束；确认v1时序算法适用、总线未被其他owner使用后，另评审CON仅更新0xff00 tuning位及CLKDIV整值的写入/读回顺序。前一adapter候选的KC_HARDWARE未就绪门禁保持，未因这次计算单测而解除。没有修改正式源码、SDK、设备、其它候选或中央日志，也没有扩展音频/唤醒/联网任务范围。

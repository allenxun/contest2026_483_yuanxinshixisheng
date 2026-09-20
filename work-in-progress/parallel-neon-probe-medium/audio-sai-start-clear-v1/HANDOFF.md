# start-clear独立单变量组件

本交付不修改或重新封存reset组件。`sc_once(port,&zero_result,true)`在root已证明静止/ampoff/codec mute/无IRQ或DMA用户的平台上，只向SAI_CLR0x14写一次3（TX逻辑clear bit0、RX逻辑clear bit1），等待两bit自清并检查两FIFO总计数为0。没有reset、CSR修改、DMACR修改、数据去零或codec操作。

依据冻结TRM Application page946明确要求配置其他寄存器之前clear TX/RX logic并等待完成。当前PIO只在结束时clear，第一轮开始没有该步骤。因此start-clear是有直接初始化顺序依据的独立实验，比“CSR需要reset锁存”的猜测更强；仍不宣称已证明它能解决四bank轮转。

root建议先显式capture-clear模式：platform clocks/power可用、codec未arm且amp低 → sc_once → 重配原SAI profile并读回 → 原capture/trace。不与capture-reset同时运行；clear完成后仍needs_reapply=1，绝不把它作为音频ready。TX/RX共用清理需要全部独占，允许清掉旧FIFO残留，不能在另一音频事务活动时使用。

预检VERSION23073576、XFER低4bits0、DMA请求位0、STATUS全idle、没有已有CLR命令。只使用CSR官方2307版本的idle语义；没有盲写其它版本。单次等待1000us，另100000poll硬上限；clock倒退/停顿或回调错误不假成功。任何写后失败保持held，阻止后续SAI流/自动重试，交root监督；成功held0仅代表逻辑清理结束，配置尚需重做。接口保留初始/末尾FIFO、CLR、时间和poll计数，供root停止后输出，无实时打印。

TRM流程图仍使用XFER[1:0]等旧文字，而详细寄存器定义实际TXS/RXS为bits2/3。本候选不照抄流程图盲改XFER，而要求全部低4bit预先为0；仅采用注释及详细CLR寄存器一致的bits0/1命令语义。未设置FSC或forced clear，未改变分频。

run.py真实Windows GCC C11 O0/O2、Wall/Wextra/Werror/pedantic编译测试通过，原始test-output.txt和输入/输出哈希齐全。模拟核对唯一写地址/值、等待自清、旧FIFO残留清除、活动/DMA拒绝、deadline/clock停顿有界、写失败/清后残留held。没有硬件/SDK/正式源码访问。完成交付后本清单与文件冻结，后续补充独立目录或新addendum清单。

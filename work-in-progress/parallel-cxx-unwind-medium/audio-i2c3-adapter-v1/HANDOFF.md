# I2C3 codec adapter candidate

已提供可编译的 codec_txn 读写适配层与基于官方源码的RK3x寄存器状态机候选，完成O0/O2主机mock测试；**硬件模式明确返回KC_NOT_READY，未写板子寄存器**。用户已确认MIC及板载喇叭连接，不再重复询问接线。没有扩展codec初始化表、SAI或功放控制，B/C负责这些部分。

## 已核对来源

正式port/app没有现成通用I2C3驱动；app/k7radio/k7radio_main.c只有I2C1/2裸寄存器只读诊断（I2C2 RTC、I2C1 PMIC）。其100ms轮询、全IPD清除/STOP参考可对照，但不能把I2C2时钟字段/引脚配置或0x300时序值直接用于I2C3，也不是跨客户端的总线锁。

音频已冻结DTS与原理图映射：I2C3=0x2ac60000，长度0x1000，GIC_SPI91；M0 SCL GPIO4_B5、SDA GPIO4_B4、mux11；codec7-bit地址0x10，非8-bit0x20。DTS引用CLK_I2C3/PCLK_I2C3、SRST_I2C3/SRST_P_I2C3。详细来源行号为rk3576.dtsi:4870起、rk3576-pinctrl.dtsi:1715起和parallel-k7-audio/HARDWARE.md。

后续主会话提供的官方归档冻结源 evidence/audio-sdk-extra-20260910 已核验全部6文件SHA256并复制进本目录inputs。i2c-rk3x.c为OID 927d9ea6c5976486c100d51ca66e3abd06c29b85、SHA256 67b6eb49cdb0838bcd00e58021847461fe4b7fa4142f15f3de3ac59ac9b17bb5。这是官方归档参考实现，不等于NuttX现有驱动已采用该实现。

| 项目 | 确定证据/派生值 | 使用边界 |
|---|---|---|
| CRU | clk-rk3576.c:583 PCLK gate12 bit2；:609 I2C functional gate12 bit14；CLKSEL57 bits5:4，parents为200/100/50/24MHz | CRU base0x27200000由DTS；按现有RK3576 GATE/CLKSEL宏可算0x27200830、0x272003e4，需HIWORD_MASK局部写，不能覆盖邻总线。此候选不写CRU |
| IOC M0 | pinctrl-rockchip.c:5238 gpio4 bankB offset0x4088，4bit pin≥4再+4；:1140位移(pin%4)*4 | IOC base0x26040000，派生GPIO4_B4/B5位于0x2604408c bits3:0/7:4各0xb。来源不是照搬RTC GPIO0字段；候选不写IOC |
| I2C寄存器 | i2c-rk3x.c:34–105 CON/CLKDIV/MRXADDR/MRXRADDR/MTXCNT/MRXCNT/IEN/IPD、TX0x100/RX0x200；REGISTER_TX模式1 | start/fill_transmit/prepare_read/setup/stop为具体流程依据 |
| version5 | i2c-rk3x.c:1711以CON version≥5识别autostop，:1176 setup清CON1 | 状态机对version≥5清0x228禁自动停止，使用显式STOP；未猜未知版本行为为已验证 |

## 文件和接口

adapter.c/h提供ka_write、ka_read，与kc_port相同读写签名；只接受地址0x10、TX寄存器+值2字节，combined read为TX1/RX1。codec_txn.h原样冻结。通过ka_backend提供共享bus trylock/unlock、同域单调时钟、非阻塞begin/poll/stop/idle；锁覆盖完整START→数据→STOP及idle确认。跨线程调用adapter对象仍须单owner串行，backend锁必须是I2C3所有使用者共享的实际NuttX总线锁，不能每个context各建一个锁。

rk3x_registers.c/h是可注入read32/write32的寄存器状态机，未安装真实MMIO函数。读用MRXADDR/MRXRADDR硬件combined机制，不拆成两个有STOP的普通事务；写把从地址、reg、value装入TXBUFFER并MTXCNT=3。成功MBTF报告有效payload TX2；MBRF报告TX1/RX1。NAK先于完成判断，即同次pending中同时有NAK与完成也不算成功。错误下精确ACK到第几个字节未知，保留保守计数，**零计数不证明codec没被部分改写**。

状态机保留现有CON tuning bits，不自己猜分频/上升时间参数；begin拒绝已有CON.EN、IEN或非idle总线。stop只处理本实例active事务，不对检测到的其它占用者发STOP。STOP pending确认后才禁controller，随后要求lines_idle回调确认为高；无法确认则保留owner，由后续有新deadline的cleanup继续处理。它没有GPIO恢复、CRU reset、IRQ注册、DMA或总线扫描。

## 失败与期限

ka_init要求零初始化新对象，拒绝重初始化活对象；本版本mode!=KC_SIMULATION一律KC_NOT_READY，且不调用总线。成功测试不自动开启硬件。硬件开启需要下一版明确集成，不能将mock的ready字段改true后声称已审硬件。

每次检查绝对deadline，与now_ms同域，拒绝时钟倒退；事务和cleanup各最多4096次poll，冻结时钟也不会无限循环。backend操作必须自身非阻塞有界，此上层无法抢占阻塞回调。该poll预算是保守测试边界，实际NuttX轮询间隔/调度和100kHz传输时间需另行验证，不能声称已获得总线吞吐或实时性。

传输错误锁定poisoned，不自动下一事务。STOP未确认则leased及物理锁保持，拒绝后续读写；ka_cleanup可给独立未来deadline，确认quiescence后才解锁，poisoned仍不清除。无用户buffer借出：begin复制值，poll返回值，成功STOP后才写回read输出，不会返回后异步使用调用者栈。

ka_cleanup只确认I2C总线，**不能接成kc_port.control(KC_QUIESCE)并返回全codec成功**；codec事务层还需要SAI/DMA停机、capture关闭和功放保持关闭。clock_ready/control/delay_ms未在本子任务实现，也没有伪造KC_READY计划。

## 主机验证与待完成项

`python -B verify.py` 使用本地主机gcc12.2，严格C11 -Wall -Wextra -Werror -pedantic，O0/O2均通过。adapter实际代码15项生命周期/有界/锁/短计数/NACK/STOP失败/超时/硬件拒绝测试；寄存器模型测试真实offset写读、W1C、write3字节、combined read、NAK优先、STOP未到/line低保留、version5清autostop。test_adapter中的寄存器数组是抽象生命周期模型；test_registers才按来源offset模拟，二者均无设备。原始命令、输出、输入哈希见run-evidence.json，全部交付见delivery.json。

待主会话/下一版：真实I2C3时钟使能及分频/CON tuning计算、复位位与保留状态恢复、pinmux写入前冲突核对、实际VCCIO/上拉与SCL/SDA读回、共享bus锁NuttX绑定、MMIO屏障、target完整编译及有界定址试验。已补到官方驱动，初期“无TX来源”不再是当前缺项；当前缺的是其向实际板端时钟/资源和错误恢复的完整集成与验证。MIC/喇叭已连接不证明这些控制器条件已满足。本交付未改正式/SDK/其它候选、未访问设备或发声。

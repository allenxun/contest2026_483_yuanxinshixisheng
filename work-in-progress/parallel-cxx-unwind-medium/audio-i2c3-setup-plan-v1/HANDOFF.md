# I2C3 prepare/restore candidate

plan.py 只生成计划，无 MMIO。prepare 仅修改 CLKSEL57[5:4]、GATE12[2/14]、GPIO4B4/B5 mux；不会改 PCLK_ROOT、父 PLL 或共享分频。首版要求原功能 gate14=1，避免在运行中的时钟上切源；已开启实例需另行核实所有权/停机，不自动接管。

精确 HIWORD 写值：0x272003e4 写0x00300030选 xin24m；0x27200830 写0x00040000开 PCLK、写0x40000000开功能时钟（合并0x40040000亦为同字段，但本计划分阶段）；0x2604408c 写0x00ff00bb选 B4/B5 mux11。不能用读改写全32位，也不能覆盖同寄存器其他 I2C 门或 pin。读回仅比较本次 mask。

顺序：持有物理总线及相关系统字段共同所有权→保存原值→功能门关闭时选源→开 PCLK→在接口可访问且reset已释放前提下检查 CON.EN=0、IEN=0→开功能门→确认控制器仍无事务、引脚可安全切换→切 mux。阶段 barrier 是必须执行的外部条件，不能过滤 barrier 后把写数组直接全量执行。开 PCLK 前无法安全读控制器时，不假造其状态；在开门后验证失败则只回退已确认写入的系统字段，不碰未知控制器。切 pin 可能带来线路跳变，即使没有 START；需要现有 pin 使用方已释放、codec供电/电平兼容、线路检查依据，不能由 mux 读数替代。

前置门禁由外部真实证据提供：共同锁/独占owner、PCLK_ROOT及其选中父分支已可用、I2C复位已释放、电源可用、pin可重新分配、板设计xin24m来源确认。缺一返回not-ready。共享PCLK不可用就停止，不为了本功能打开/切换共享父链。主机 bool仅是接口要求，不是这些事实已经证明。

reset：冻结官方 i2c-rk3x.c:1198–1211 实现 i2c和apb reset assert→10us→deassert；:1310–1314 仅在超时且 SLV_HDSCL 条件下调用，然后重设分频。probe :1654/:1663 获取reset句柄，但不是每次prepare强制reset的依据。因此本候选不含reset写入，必须另外确认当前reset释放；若状态未知/控制器残留busy，停止并另评审专用reset恢复，不照搬错误恢复作无条件初始化。reset会清除控制器寄存器，无法靠恢复CRU字段撤销；也不保证释放外部设备拉低的线。本交付不猜reset位号，不写reset。

timing：DTS xin24m节点明确clock-frequency=24000000，这是板设计/固件声明值，不是实测。可以把经主会话确认的板设计24MHz作为标注来源的工程输入，无需要求用户新购测量工具；不能声称实测精度。既有i2c3_timing候选仍要求输入Hz、目标SCL及rise/fall约束已知，未知边沿不能偷偷填测试100ns。prepare不编程CLKDIV/CON tuning、不将clock选择成功称codec ready；时序写入、STOP/线路idle和电气约束在后续独立阶段。

恢复：停止新事务、确认IRQ/poll/控制器访问结束、无pending START/STOP或DMA等活动，保持共同锁。记录每个成功写入且读回匹配的操作。restore先检查所有已写自身字段与预期一致，任一冲突返回错误，不生成盲目回滚；未确认的写必须先读回消除不确定性。逆序恢复mux→功能gate→PCLKgate→source，仅HIWORD恢复原字段；原PCLK已开则保持已开，不强制全关。支持每个成功前缀的失败恢复，不改变旁邻字段。恢复每步仍需读回；restore生成不是恢复完成。锁若不被所有其他写者遵守，compare/write间仍有竞态且无法识别ABA；冲突时保留owner并交外部监督，不擅自覆盖。若后续加入timing/CON写，应先在PCLK可用时恢复控制器自身状态再关闭门；本计划不能代替那份控制器回滚日志。

本交付仅纯计划与合成主机测试。没有执行MMIO，未启用I2C/codec/SAI，未更改正式源码/SDK/设备/日志。输入原样快照与哈希见inputs.json；复现 python -B test_plan.py，原始stdout/stderr及退出码见run-evidence.json；完整清单delivery.json。

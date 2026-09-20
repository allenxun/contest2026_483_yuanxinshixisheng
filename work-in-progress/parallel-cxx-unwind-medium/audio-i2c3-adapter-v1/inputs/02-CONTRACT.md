# C11 codec 事务层与移植契约

本目录是可审查的主机事务层候选。编译/故障测试执行真正的 `src/codec_txn.c`；默认 `kc_es8388_reference()` 是参考来源占位配置，`kc_start()` 返回 `KC_NOT_READY`，零设备访问。没有可默认执行的实板录音序列，也没有I2C3/SAI/DMA硬件实现。

## 调用与所有权

1. 调用方静态分配 `struct kc_context` 与 `kc_port`，先 `kc_init()`。只能在初次未使用内存上初始化；不能重初始化未退出的上下文。全程无动态分配，freestanding对象依赖memcpy/memset。
2. `kc_start(context, plan, absolute_deadline, &id)` 验证后将整个固定容量plan复制到上下文，外部后改plan不影响执行。最大64步/16个可读规则；当前仅接受16kHz、2×16bit请求profile。事务编号自1递增不复用，UINT64_MAX后拒绝；失败配置不消耗ID、不改输出ID、不调用设备端口。
3. `kc_poll()` 每次最多调用一个控制、clock-ready、读、写或delay端口，不在核心中做无限重试。OFF→POWERING→INITIALIZING→PREPARING→READY。READY表示已审核的路径准备端口返回成功，不代表已经录到PCM。READY仍保留资源和事务deadline；后续poll遇到截止仍转STOPPING。
4. `kc_cancel(id)` 只标记取消，`kc_stop(id)`显式进入STOPPING。正在同步bus调用时，只有同一线程回调内的cancel允许重入；其它重入操作返回BUSY。截止、错误或取消后不会执行后续配置，也不会报告READY。STOPPING只由`kc_cleanup(id,new_deadline)`调用下层quiesce，确认退出后才能离开。原错误在result中保留，清理结果单列cleanup_result。
5. 正常停止/取消且无时钟故障后回OFF；其它失败在清理完成后进ERROR，需`kc_reset_error()`确认后才能重试。时钟倒退锁定ERROR，禁止普通reset_error重新开始；需主服务确认更换时钟域并安全重新建立上下文。总时限等于当前时间视作过期，截止在同刻结果之前生效。

**线程契约**：所有调用来自同一个串行服务任务；`in_call`只是防回调重入，不是SMP锁。跨线程取消必须排队发消息给该任务，不能直接并发修改context。同一物理codec地址只能有一个context/owner；总线若还服务其它器件，下层用I2C互斥保护完整combined transaction。不能创建第二个context规避BUSY。C对象没有析构保障，不可在STOPPING时丢弃、清零或释放其后端资源。

## 下层必须实现的六个端口

| 端口 | 必须保证 |
|---|---|
| now_ms | 单调uint64毫秒，与所有绝对deadline同域；不得依赖可被校时的墙钟 |
| write | 地址是7-bit 0x10，不左移；传输寄存器地址+数值两字节，分别报告tx_done=2/rx_done=0；任何短传输或OS错误均报告 |
| read | 只对已经审核的可读寄存器使用；完成寄存器选择TX1与数据RX1的combined transaction，分别返回实际长度；不能把“两个消息”当“两字节” |
| delay_ms | 在deadline内等待至少请求时间，错误返回非零；核心用时钟复核，提前返回是KC_DELAY_ERROR |
| clock_ready | 验证/等待所请求sample_rate/MCLK/BCLK的目标时钟和格式条件；零必须代表实际满足，不能只是发起使能请求 |
| control | POWER_PREPARE建立已审核的电源/禁用功放/安全基线；CAPTURE_PREPARE确认路径准备；QUIESCE停止所有旧I/O/DMA并确认capture关闭、功放保持关闭；不能仅发cancel就返回零 |

所有设备端口都接收绝对deadline，下层负责I2C控制器等待、ACK/NACK、仲裁丢失、超时、STOP/restart、短消息检查以及缓冲生命周期。核心无法抢占阻塞I2C调用；只能在返回后拒绝迟到结果。下层即便报错，也可能已改动寄存器，所以任何访问错误都需清理。回调不能保留栈buffer指针、longjmp或在返回后继续异步使用它；若平台API异步，适配器必须等到完成/终止确认再返回。

上层超时后仍可给cleanup独立期限以便恢复；没有确认则保持STOPPING，忙碌重试不得释放DMA。即使清理确认是零，迟到/时钟不一致结果也保守拒绝并保留租约；此时下层quiesce须可重复调用。新一轮POWER_PREPARE要从已知基线重建，不能假定前次部分写入已自动逆转。

## 配置审核与读回边界

plan与port的mode必须相同；SIM_ONLY步骤只能搭配SIMULATION端口。HARDWARE计划每步和每个可读规则都需TARGET_REVIEWED，以及六项reviews全部通过：identity、rails、clock、format、analog、stop。source_id为本地来源台账键。审核位是可信集成者的声明，不是运行时自动证明、更不是安全隔离；不能仅改标志来代替资料/实板审核。

读回必须显式登记寄存器、允许掩码、来源ID；step.mask只能是允许位的子集、expected不得含mask之外的位。没有规则即拒绝该配置，验证发生在任何设备调用之前。默认ES8388参考没有可读白名单；Linux使用regmap read/cache并不能证明每个寄存器每个位允许硬件读回。没有“先写整个值再随意读回”的隐式RMW。保留原始port_error、tx_done/rx_done及failed_step/failed_phase，清理错误独立保存cleanup_port_error，便于区分电源、时钟、配置步及准备阶段失败；核心不输出凭据或非必要数据。

`KC_REFERENCE_ONLY`仅表示原始官方源码确有该语句；`KC_TARGET_REVIEWED`才可由后续主会话在证明适配目标后构造。默认示例只列CONTROL1的两次reset参考写，缺少capture步骤且reviews不完整，永远不默认运行。功放使能动作不存在于本候选；Linux空mute未被用作任何静音保障。

移植顺序：先实现并单测超时有界的I2C3适配器与控制端口→补齐PROVENANCE.md中的资料和实板测量→产生独立审核过的录音计划/可读白名单→使用原测试C代码替换端口做有界板测。不得先默认启用参考probe表。与audio upper/lower-half、实际DMA录音和VoiceLink连接是后续集成，不是本事务层验收范围。

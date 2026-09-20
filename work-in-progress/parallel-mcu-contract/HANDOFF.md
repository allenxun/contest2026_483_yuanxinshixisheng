# MCU contract 离线候选交接

本交付仅在 `work-in-progress/parallel-mcu-contract` 写入。实际可核实身份为本次代理任务路径 `/root/mcu_contract`；未获得独立会话 UUID 或模型标识，不推造身份及 JSONL。未访问任何硬件、串口、SDK、Ubuntu、私密配置，未改正式源码、中央日志或其他候选，未提交推送。

## 已交付与复现

`contract.py` 提供现有7字节线格式编解码、增量滑窗解析、有界收包队列、有界发送事务模型、显式断线/超时/停止及纯数学PWM/PID模拟。无真实传输后端，不会打开设备。Session 为单所有者对象，时间由调用者提供，单调毫秒。事务队列和结果历史均有界；历史满时淘汰最早记录，审计消费者须及时取走结果。

命令（从任意目录运行）：

```powershell
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B E:\openvela\VelaVision\work-in-progress\parallel-mcu-contract\run_tests.py
```

每次运行生成独立 evidence 时间目录。`evidence-20260910T065849603780Z/result.json` 为通过记录：22项单元测试，涵盖65536个有符号值、100万字节确定性噪声、全部14字节帧分割点、结构破坏、重叠头、保留字节、溢出、超时边界、部分写、断线清空不重放、序号耗尽、停机及数学模拟。MinGW GCC `-std=c11 -Wall -Wextra -Werror` 编译从真实 `gimbal_link_pack` 提取的原函数，4组黄金/边界向量与候选一致。每个子进程60秒上限，原始stdout/stderr及命令/退出码均保留。首次 `evidence-20260910T065830828583Z` 的C测试壳因缩进警告失败（单元测试通过），修正测试壳后通过，失败未覆盖。

输入路径和SHA256见各轮 `inputs.json`；测试结束再次哈希核对均无变化。输出文件及SHA256见 `delivery.json`。delivery不包含自身哈希，外部协调者可对其计算。交付冻结后请只读核对；重跑应单独协调以免改变目录清单。

## 真实源码合同

- RK3576物理UART6/openvela `/dev/ttyS1`，115200、8N1、无流控；STM32 USART3部分重映射PC10 TX/PC11 RX。接线描述来自现有文档与初始化代码，本轮未验证电气连接。
- 每轴 `55 AA axis lo hi reserved FA`，axis=00/FF，目标有符号16位小端；发送X后Y。正常主机reserved=00，当前MCU解析接受任意reserved。该字段不是校验，也不是协议版本。
- `encode_pair` 精确遵循 `gimbal_link_pack` X[-800,800]、Y[-200,1030]。`gimbal_link_adopt` Y下限为-120（X范围相同），旧set命令另有窄范围；这三个入口合同不同。codec编码范围不是动作准入范围，更不授权机器人动作。robot-tools默认关闭的动作不联接本模块。
- `DataDecode1` 当前源码已经是静态7字节滑窗、轴与尾校验；`app/gimbal/README.md` 的旧6字节越界叙述与当前代码不一致，本交付不修正式文档，也不推断板上STM32镜像版本。
- MCU `main -> mode_1 -> get_point2_p -> Servo_ApplyLegacy`；get_point2_p按RINGBUFF_LEN限制每轮排空，逐轴更新最后请求。X/Y不是原子事务，丢失半对可能混合新旧目标。主机Session对部分写故障标为未知，不会回滚设备。
- 未发现USER/BSP业务CAN初始化、收发或消息定义；FWLib存在`stm32f10x_can.c/.h`只是厂商通用库。CAN状态为 **unsupported**；没有CAN适配成功、带宽或实测结论。

## 状态、确认与停止

原协议没有MCU ACK、状态、测量位置、线序号、CRC、禁能或急停消息。相应CAPABILITIES均为unsupported。解析器用于离线命令流分析，不把收到的相同形状数据当设备状态或确认。

Session sequence 是仅驻留主机的uint64事务标识，线上不增加字节，终身不回绕；重连不重置计数，耗尽拒绝新任务。`host_write_complete` 仅表示模拟传输接受了14字节，绝非MCU收到/运动完成。`acknowledge()`明确抛NotImplementedError，不关联未知回包。

无校验意味着合法形状的payload bitflip不可检出，测试明确演示10变11仍合法。滑窗恢复不能保证任意噪声不产生误帧，也不能检测重复、丢序或重放。gap_ms=50是候选主机解析超时策略，现有MCU解析无同等超时清空保证。

`halt()`取消待发、断开本地主机状态，任何已接受字节都可能已影响设备；不发零位、不禁用PWM、不保证机械停止。正式 `k7host halt` 文本确认的是板端跟踪请求，非MCU ACK。`zero`是移动目标，不能作为急停。设备实际位置/连接/运行状态本轮均未知。

## PID/PWM范围

当前bsp_init初始化TIM2硬件PWM，不启动PID定时器；主循环直接应用旧目标，不提供实测角度反馈。`pid.c`保留位置/增量PID数学实现，但不是当前闭环运行证据。候选pid_step仅模拟位置式积分±7000限幅，使用Python浮点而非STM32 float位级重现；未模拟完整控制系统，也未调任何参数。

当前Servo_ApplyLegacy按C整数向零截断：X=1492+(-x*12/10)限[500,2500]；Y=700+(y*15/10)限[500,2300]。TIM2配置1us计数/周期19999/50Hz，PA0/PA1输出，保持脉冲。模型验证中点、负数截断和饱和，不能证明真实频率/机械极限/安全性。历史阻塞Servo_J函数仍在源码，不将其当当前主路径。

## 未完成与接续边界

尚未集成正式主机或板端；无真实UART接收遥测协议、ACK/CRC/序号/握手/急停方案或CAN驱动；未编译STM32或openvela、未验证中断竞争、实际波形、执行机构或闭环响应。只编译了真实主机pack纯函数，MCU解析与PID/PWM为源码对照模型测试，并非整个固件测试。需要新协议时应单独设计显式版本化候选，不能挪用legacy reserved或伪造兼容应答。未知实际STM32固件哈希须由后续授权流程核实。

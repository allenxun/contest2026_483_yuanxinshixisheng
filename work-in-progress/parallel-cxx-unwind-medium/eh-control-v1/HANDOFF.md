# k7ehcontrol 最小区分候选

仅新增本目录，未改旧concurrent-probe-v1、正式app或异常运行库。冻结输入SHA256为 `667527d784ab9a80a7bc880a0c0d32818c051bc55c9949592edfec1bd6085536`，input.json记录路径；prepare.py校验该哈希后仅在本目录派生源码及control-diff.patch。后者是审阅差异，不自动应用。

## 两个模式

| 新启动后命令 | 协调线程预热 | worker | 每worker异常数 |
|---|---|---|---:|
| k7ehcontrol single | 无 | slot0绑定CPU5 | 1 |
| k7ehcontrol warm1 | 完整同一one_throw三层自捕获，检查计数并输出/flush PREHEAT_PASS | slot0 CPU4、slot1 CPU5 | 1 |

single的创建数、ready门参与者及完成等待均为1，不会留下等待不存在第二线程的barrier。单worker仍标识payload worker=0，但请求CPU5；warm1与原双worker标识一致。新增requested_cpu字段只用于亲和性及输出，三层noinline leaf/middle/outer、Guard和one_throw函数体保持原样，不改变其异常处理逻辑。

warm1预热在创建任何worker之前进行：期望caught=1、cleaned=3、errors=0，失败输出PREHEAT_FAIL并返回22；运行库直接abort时可能连PREHEAT_FAIL也到不了。只有成功后输出 `PREHEAT_PASS caught=1 cleaned=3 workers_created=0` 并flush，再创建worker。该明确标记区分“主线程同路径失败”和“预热已完成后worker阶段失败”。每个成功worker应caught=1/cleaned=3，errors/cpu_mismatch均0；成功汇总必须有created=joined=1或2。

同一启动只能调用此应用一次，两个模式必须分别新启动；不要先运行旧k7cxx/k7eh或其他展开探针。single只保证此候选不预throw，不证明整个系统此前未查过FDE。亲和性在pthread_create前设置，目标分别CPU5或CPU4/5，16KiB工作栈。主线程建议16KiB；实际栈余量需板端验证。

接入是新增独立应用，入口 `extern "C" int k7ehcontrol_main(int,char **)`。示意：

```cmake
nuttx_add_application(NAME k7ehcontrol SRCS k7ehcontrol_main.cxx STACKSIZE 16384 PRIORITY 100)
```

主会话负责应用配置/源码清单及独立构建；目标须使用__NuttX__分支、异常支持和CPU4/5在线。禁止目标定义K7EH_HOST_TEST及故障注入宏。没有增加启动时自动执行行为。

## 所有权与失败规则

沿用原joinable线程、静态参数/状态和失败回收逻辑。第0次创建失败无线程；第1次创建失败会合作停止并join第0个。只在所有已创建线程成功join后返回。合作就绪/运行等待5秒级预算、宽限2秒；无法合作结束或join错误时进入REBOOT_REQUIRED保持任务所有权，不能强杀展开中的线程。pthread_join自身及TLS析构仍可能阻塞，必须有主会话外部截止与基线恢复方案。

**运行库abort可能直接结束任务组并绕过全部合作清理。** 此时没有最终joined输出，就不能从ps不见线程宣称正常回收；这正是原cold失败所保留的边界。探针不实施外部重启、硬件操作或异常库锁修改。

## 原始主机验证

`python -B run_host.py`在本目录复现5个 `g++ -std=c++17 -O2 -Wall -Wextra -Werror -pthread` 严格构建及9个运行案例；含编译器信息共15条命令，host-results.json保留命令、退出码、原始stdout及文本断言。全部通过：single、warm1打印/计数/参与者、PREHEAT_PASS输出顺序、同启动拒绝、旧cold参数拒绝、线程0创建失败、只注入第1次失败时single不受影响、warm1第1次创建失败回收、合作就绪超时回收、计数错误拒绝（其中正常案例合计按脚本实际9次运行计）。

宿主为Windows x86_64 GCC12.2，POSIX线程/SEH异常；目标为ARM64 GCC13.4 single-thread libgcc/DWARF。主机只验证控制逻辑、清理的正常/合作失败路径与打印，不证明目标无FDE搬移/寄存器尺寸表初始化竞态。目标未编译、未上板，不能依据本交付宣布修复。

## 结果解释

single也失败：两个探针worker重叠不是必要条件，优先看同链单线程展开、worker环境及精确abort分支。warm1预热先失败：同一三层链在主线程已经失败。single与warm1通过但原cold失败：支持首次共享初始化方向，但仍没有现场分支证据，不证明根因或通用线程安全。warm1通过仅是受控预热后的功能样本，不是永久加锁替代。

所有文件和主机构建产物由delivery.json逐一标识；未访问SDK/VM/硬件或中央日志。

# 共享 Wi-Fi 调度主机候选交接

本次委派范围完成，等待主会话核对集成。新增线程安全固定容量请求/事件队列、BLE/VoiceLink 固定身份入口和单所有者 pump；后端提交位于队列锁外且契约要求非阻塞。没有接入真实 WPA/DHCP 或运行于 openvela。

- 实际会话：`01a0892e-2964-7ec3-bd76-9ab4937980cb`。
- 会话工作目录：`E:\openvela`；唯一开发输出：`E:\openvela\VelaVision\work-in-progress\parallel-wifi-dispatch`。
- 主会话：`01a07ed4-3f0d-7450-8bb1-bb756849cb4e`，负责 SDK、硬件、正式集成和中央日志。
- 输入记录：`input/sources.json`，18 份实际源码/接口/回归测试输入及 SHA-256。当前原始文件复核结果见最终证据目录的 input-verification.json。

变更清单：include/wifi_dispatch.h、src/wifi_dispatch.c；src/wifi_broker.c 对 OWNED 收到离线但尚未退出的最小修正；tests/test_dispatch.c 真实 pthread 用例；只读来源复制的 test_broker.c；脚本和 CONTRACT.md、INTEGRATION.md。include/wifi_broker.h 保持来源原样。`candidate.patch` 包含新增调度源码/测试和相对 input/src/wifi_broker.c 的最小 broker diff，使用组件相对路径，仅供主会话审查映射，不能直接套到仓库根。`delivery.json` 为本目录交付文件哈希（不含其自身），并保留原始输入与历史测试输出。

复现命令（PowerShell，进入本目录）：

```powershell
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 scripts/test.py
```

编译器默认 `D:\software\mingw64\mingw64\bin\gcc.exe`，GCC 12.2.0 / MinGW POSIX pthread，可用 WD_GCC 指定等价 GCC。脚本每次建立新的 UTC 证据目录，每个编译/执行子进程限时 30 秒，保留精确命令、返回码、耗时、原始输出和源码 SHA。不得重新运行一次性 snapshot 脚本覆盖输入。

最终证据：`evidence/run-20260910T060821490477Z/`。O0/O2 均启用 C11、Wall/Wextra/Werror/Wconversion/Wshadow/pedantic/pthread；各执行 200 轮两个真实客户端线程竞争，另有 12 线程并发满队列、后端线程并发投递。模拟时钟、模拟网络后端，真实线程执行候选 C 代码。测试覆盖进度不等于成功、身份拒绝、请求票据唯一、队列满取消、完成事件满队列重试、late IP、过期序号、旧事务、清理期间重试 BUSY、运行/排队超时、提交失败、未证明旧网络空闲、凭据缓冲擦除和回调重入不持锁。原 broker 回归测试也通过。具体检查次数以原始 test-*.log 为准；没有运行 TSan，不宣称穷尽所有交错或 NuttX SMP 验收。

首次严格编译发现测试代码 for 同行语句触发 misleading-indentation，已修正后通过；该失败留在真实会话工具输出，不伪造历史文件。早期通过记录 run-20260910T060504874332Z、run-20260910T060557905252Z 保留，但不能替代最终版本结果。broker 离线先到修正及其依据详见 CONTRACT.md。

仍依赖主会话：NuttX 锁/64 位时钟/唤醒端口、专用连接工作槽、真实 worker 退出监督、维护租约移交、失败 CLOSE 清理围栏、完成事件保留重试、BLE epoch/协议回包、CLI/scan 禁止旁路、SDK 编译和有界板端联调。成功不代表互联网可达；取消返回不代表资源已释放；清理失败宁可持续 held，不抢占硬件。

本轮没有硬件、COM8、蓝牙、Ubuntu SDK、sync_sdk、固件、私密配置、中央日志修改或提交/推送。AI 日志由主会话核对该实际会话的自动采集并用原版官方校验器验证，最终归入同仓 logs/maomaojiang01；本目录不手写 JSONL，不声称本轮最终日志已由本会话验证。

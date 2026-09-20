# 离线控制输出验收器

仅处理一次 single 或 warm1 调用的完整输出。没有运行 SDK、网络或设备命令，没有修改冻结探针或正式源码。

使用 Python 3.6+，无第三方依赖：

```powershell
python -B accept_output.py <runtime.bin> --mode single --scope target --output single-acceptance.json
python -B accept_output.py <runtime.bin> --mode warm1 --scope target --output warm1-acceptance.json
python -B test_accept_output.py
```

退出码 0 表示文本条件满足，1 表示拒绝。输入文件 SHA256 与字节数写入结果。`--scope` 必须显式指定：host 要求观测 CPU 为 -1；target 要求 single 的 worker 0 在 CPU5，warm1 的 worker 0/1 分别在 CPU4/5。主会话应将 target 结果与实际加载镜像哈希、独立启动记录及原始串口文件绑定；工具不能认证来源。

检查唯一 begin/result、模式与 rounds/workers/main_prethrow、PREHEAT_PASS 数量与先后、每个 worker 唯一 ID、caught=1/cleaned=3/errors=0/cpu_mismatch=0、请求与实际 CPU、时钟区间以及 created/joined 精确数量。single 禁止预热记录；warm1 必须在 worker 输出前出现 caught=1/cleaned=3/workers_created=0 的预热成功记录。额外失败/未知探针记录、重复字段、缺失记录及常见崩溃诊断均拒绝。

保留通用串口背景行，去除 ANSI CSI 与行首尾空白。与其他文字交织的探针记录拒绝；不会尝试修补截断串口。输入应为所选启动的完整运行窗口，不能手工删除失败行后充当通过。常见崩溃词匹配可能保守拒绝包含旧诊断的混合日志，应保留原始日志并明确另选的调用窗口范围。

验证使用冻结 eh-control-v1/host-results.json 的 9 次真实主机执行输出，以及 32 个显式合成案例，共 41 案例；另有 2 次 CLI 退出码检查。test-results.json 保存每个案例的原文、哈希、来源标记、预期与实际判定。host-single.txt/host-warm1.txt 是冻结 JSON 中字符串的 UTF-8 导出，不是新运行或目标串口证据。合成 target-like 文本只测试 CPU 验收分支，绝非真机通过。

局限：输出先后仅证明输出顺序，PREHEAT_PASS 的语义依赖冻结源码；打印间隔重叠不证明两个 unwind 实际并发。该工具不证明系统全局 unwinder 冷状态、不证明 abort 后所有权清理，也不证明 libgcc 线程安全。主机为 Windows POSIX-thread/SEH 编译器，而目标为 GCC13.4 single-thread libgcc；主机逻辑验证不能跨越此边界。缺少最终 joined/PASS 的故障记录必须拒绝，不能由 ps 中线程消失推断正常清理。

随后收到主会话提供的真实控制记录，使用 check_frozen_target.py 只读验收，结果见 target-results.json：single 的 CPU5/caught1/cleaned3/joined1 满足；warm1 的预热顺序、CPU4/5 各 caught1/cleaned3、joined2 满足，打印时间区间重叠。原 cxx-eh cold 记录因崩溃诊断及缺少控制协议成功记录被拒绝；这是旧协议故障样例，不能称为同版 eh-control 的失败。三份原始输入字节数与 SHA256 已冻结，未修改原始记录或访问设备。

未完成项：固件哈希与独立启动关联由主会话负责。以上文本验收不能将 single/warm1 的有限通过提升为目标 libgcc 的通用并发安全结论。

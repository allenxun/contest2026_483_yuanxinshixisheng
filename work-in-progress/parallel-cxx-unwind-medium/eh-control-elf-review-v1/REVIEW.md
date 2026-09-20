# eh-control-20260910 静态接入核验

本轮核验通过；不代表目标异常运行通过。唯一写入本目录，未操作VM、SDK或硬件。

- 正式控制源码、冻结eh-control-v1候选、构建报告和主会话回传实际TU预处理记录的源码哈希均为 `bdf264d28daa30fabfae810616975774123a91ae762e3c740eee8f3fdf6b9652`。
- ELF哈希 `a83ae79abbebb02ebf21c46c76d07577f6a48b535727ec99b1ce185b83206180`，bin哈希 `bc1ec4b367e5eb46f3f629ef69658aae316cbb938f0eb4627b22d39f9cecdf29`。ELF/bin/.config尺寸及哈希与构建报告一致，各PT_LOAD文件字节与bin对应地址逐字节一致。
- ELF内 `k7ehcontrol_main=0x404568dc`，大小1220字节。g_builtins的0x404fa108记录指向名称k7ehcontrol、入口0x404568dc、priority100、stack16384；single、warm1、PREHEAT_PASS及完整usage字符串存在于可加载段。不是仅在调试信息中出现名字。
- 独立重跑原ELF审计：2CIE/273FDE通过，_sinit首槽=0x4044b088，准确指向k7_unwind_initialize，先于其他构造；异常表保留、零终止和只读范围检查通过。该检查不重新证明运行时调用和所有落点语义。
- **未启用宿主或故障注入分支。** 主会话采集的control-compile.json与上述源码/ELF哈希绑定，实际TU命令为ARM64 g++、gnu++17、-Os，含-D__NuttX__和-Dmain=k7ehcontrol_main；同参数-dM退出0。宏结果明确__NuttX__=1、K7EH_FAIL_CREATE=(-1)，K7EH_HOST_TEST、K7EH_SLOW_READY、K7EH_BAD_COUNT均未定义。ELF DWARF宏也一致。注意FAIL_CREATE宏本身正常定义为-1，不能误写成“该宏完全不存在”。

证据为review.json、unwind-audit.json、macro-scan.json、compile-macro-check.json及symbols.txt；delivery.json冻结当前文件哈希。control-compile.json由主会话采集，本代理仅核验本地内容，没有自行执行远端预处理。

剩余风险：新启动single/warm1尚需主会话实际运行；旧cold的两个共享初始化窗口没有在此修复。PREHEAT_PASS只是完整预热路径成功标记，不能推出通用并发安全；直接abort可绕过join，外部监督/恢复规则仍适用。图计算通过不替代异常展开验证。本审查不修改正式加载门禁或授权加载。

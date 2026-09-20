# ARM64 C++ unwind 最小候选（独立 medium 审查）

正式源码未修改、SDK 未访问、镜像未构建或上板。唯一写入范围为本目录。已恢复执行后完成此候选；先前暂停时目录为空。

## 已确认的问题

输入 `artifacts/cxx-tls-20260910/nuttx` SHA256 为 `8f05f77a611aa7c2940aa139521595dcd534b7030b7992f295d17afb2e0e7a3a`。基线门禁真实输出见 baseline-audit.json：没有 `.eh_frame`，33 个 `.gcc_except_table.*` 孤儿节存在，首个初始化指针为 `0x404543f4`（`_GLOBAL__sub_I_k7cxx_main`）。`__register_frame` 虽已链接，不能据此推断已经注册。`.debug_frame` 不替代运行时 `.eh_frame`。ELF `.comment` 标识 GCC 13.4.0。

正式 dramboot.ld 明确丢弃 `.eh_frame`，只读范围 `_srodata.._erodata` 在孤儿 LSDA 之前结束。board/CMakeLists.txt 固定使用此脚本；src/CMakeLists.txt 已明确链接 appinit.c，无需增加编译目标。k7cxx 有实际 throw/catch/RAII 路径，不能直接运行该基线期待异常成功。

## 候选的准确行为

candidate.patch 只涉及 dramboot.ld 和 kickpi_k7_appinit.c，candidate-* 是便于评审的完整文本；prepare_candidate.py 只从主项目读取并向本目录输出，不自动应用。

1. `.eh_frame/.eh_frame.*` 用 KEEP 保留到独立输出节，起点8字节对齐，末尾显式 LONG(0)。libgcc 通过零长度记录停止，而不是通过链接结束符。若 crtend 或其他输入早早带入终止记录，门禁会拒绝其后非零内容，避免悄悄漏掉后续FDE。
2. `.gcc_except_table/.gcc_except_table.*` 统一 KEEP 到独立节。两个节均分配给 rodata PT_LOAD，`_erodata`、`_szrodata`、`_eronly` 在它们之后，最终页对齐，因此包括在原有只读 MMU 映射范围，而不是仅靠 ELF ALLOC 标志。
3. appinit.c 内的C函数及专用函数指针放入 `.k7_unwind_init`。链接器在 `_sinit` 之后、所有排序构造表之前 KEEP 此槽。因此不依赖 constructor(101) 与其他优先级的相对关系，也不占用编译器保留的1–100优先级。
4. NuttX 正常 lib_cxx_initialize 调用首槽时执行 `__register_frame(__k7_eh_frame_start)`；必须由主集成者确认此时 heap、基础线程锁可用，并且构造循环串行。静态 bool 仅防止串行重复注册，不是SMP once原语；不得从多个任务主动调用注册函数。
5. 不在 board_app_initialize 函数体里注册，该调用点可能晚于全局构造。不在裸机早期 board init 注册，GCC 的 __register_frame 会分配 object。表和注册记录存活整个静态固件启动周期；不在 k7cxx 返回或任务退出时注销，也不安装析构注销。RAM整镜像重启由BSS重置开始新生命周期。本候选只支持当前 flat 静态镜像，不支持模块卸载/保护构建。

## 主会话集成门禁

- 先核对 input-source-hashes.json；本地原文件为CRLF，普通 `git apply --check` 因换行不匹配失败，`git apply --check --ignore-space-change work-in-progress/parallel-cxx-unwind-medium/candidate.patch` 已真实通过。最终应用由主会话执行，需检查增量。
- 核对实际SDK版本的 heap 初始化 → lib_cxx_initialize → 普通构造顺序；主会话已提供 lib_cxx_initialize 只遍历_sinit.._einit 的事实，本代理未访问SDK。不能用上游master替代实际版本证明。
- 独立新版本编译链接后运行 `python -B work-in-progress/parallel-cxx-unwind-medium/audit_elf.py <新nuttx> --output <新证据路径>`。0仅表示静态门禁通过，非运行验收；1拒绝，2不支持/结构错误。门禁核对ELF64/AArch64、FDE/CIE记录引用与终止、非空LSDA、无孤儿LSDA、只读文件装载段、MMU只读边界、首初始化槽及起止符。保留原镜像不得覆盖。
- 用实际 ARM64 objdump 确认 k7_unwind_initialize 中调用 __register_frame（包括优化后的尾调用），并核对函数入参为表起点；检查 lib_cxx_initialize 的遍历方向和执行点。当前Windows MinGW objdump不支持此ARM64反汇编，已如实记录失败。检查 libgcc `_Unwind_Find_FDE` 后端/构建线程锁策略；不能只凭符号名假定SMP安全。
- 用工具链 readelf --debug-dump=frames 或等价方法核对FDE覆盖 k7cxx throw/catch/清理路径、libc++abi 与相关库帧及有效LSDA地址。本审计脚本不解码完整DWARF指令，不声称证明了所有调用链覆盖。
- 之后才由主会话决定RAM加载：先确认启动到NSH，再运行一次k7cxx并保留 throw→catch+RAII 结果。要证明构造阶段异常工作，应独立加入构造内部自捕获的throw/RAII探针，不能让异常逃出全局构造；当前startup只写常量，不能证明构造阶段异常。扩展为跨函数栈帧清理和工作线程内部自捕获的异常探针，不能跨线程传播异常。无线恢复/验收和硬件操作完全归主会话。

GCC __register_frame 的 malloc 失败没有可传播的错误返回；这是启动时潜在致命分配风险。候选没有照抄私有 struct object ABI 或伪造缓冲区。如果希望消除此分配，需锁定当前GCC私有ABI另行评审 __register_frame_info 静态对象方案，不能擅自猜测其大小。注册后 libgcc 仍可能延迟分配排序表，第一次和并发异常的行为必须实测。

## 已执行的本地主机验证

test_audit_elf.py 构造合成ELF验证6种状态：正常、可写段、非零终止、非法CIE后向引用、超出MMU范围、首槽优先级错误。第一次测试发现终止处覆盖错误标志的问题，已修复并重跑通过。合成通过不是修复固件。run-evidence.json 保存真实命令/退出码/输出及输入输出哈希。未编译候选、未验证真实修复ELF、未进行任何真机操作。

## 来源和边界

- [GCC 13.2.0 固定发布源码 unwind-dw2-fde.c](https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-13.2.0/libgcc/unwind-dw2-fde.c)：本轮web读取成功，138–148显示注册入口分配对象再注册，后续注销释放该对象。仅用作相邻版本机制参考，实际输入是GCC13.4.0，不能冒充完全同版。遍历按零长度停止也是该实现的约束。
- [GCC 13.4.0 对应源码目标](https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-13.4.0/libgcc/unwind-dw2-fde.c)：web缓存读取失败；直接下载TLS认证失败，没有成功取得或伪造哈希。精确源码需主会话从工具链来源核对。
- [NuttX nx_start.c 上游master](https://raw.githubusercontent.com/apache/nuttx/master/sched/init/nx_start.c)：仅一般启动背景，非当前SDK证据。
- 实际SDK基线来自已读project-manifest.json，commit e987a81c32cab008d1a8521669e5488d00271322。固定commit的lib_cxx_initialize.c/nx_start.c/nx_bringup.c直接下载均TLS认证失败，web对固定commit读取也失败。未获得这些文件，不声明完成启动顺序验证。

交付没有中央日志写入、提交、板端状态更新或远程操作。所有实测结论仍沿用主会话对应固件证据。

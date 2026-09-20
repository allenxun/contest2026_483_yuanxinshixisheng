# 模型只读文件接口候选交接

状态：独立 C11 候选，未集成 llama、未编译 NuttX、未上板。唯一写入目录是本目录；正式源码、vendor、SDK、硬件、中央日志均未改动。

## 基线与目标

依据 parallel-llama-b0 的 DEPENDENCIES.md 与固定 b5046 / 74d4f5b041ad837153b0e90fc864b8290e01d8d5 源码。上游 src/llama-mmap.cpp:163 起非 Windows llama_file 使用 fopen/ftell/fseek(long)/fread；本候选采用显式 uint64_t 长度/绝对偏移，避免隐式 long 缩窄。未替换上游类、GGUF 元数据 FILE* 路径、分片路径解析或写出接口；不是完整 loader。

model_reader.h 是无分配接口。mr_file 必须 MR_FILE_INIT 初始化，不可复制，不可跨线程并发访问；所有权由调用者持有。open 必须提供精确预期长度、最大文件长度和单次读取预算。拒绝零长度、超 INT64_MAX、超预算；读取以 64KiB 系统调用块进行，先用差值校验范围，避免 offset+len 溢出。mr_seek 只接收绝对偏移；上层 SEEK_CUR/END 必须单独进行有符号算术校验，不能直接强转。

Windows 使用真实 CreateFileA 只读句柄、_open_osfhandle、_fstat64、_lseeki64、_read、_close；禁用 mmap。只接受 ASCII 普通绝对驱动器路径，拒绝 UNC/NT namespace、ADS、DOS设备名、路径穿越、尾点/空格和最终 reparse point，检查句柄磁盘类型及普通文件模式。路径过滤测试只传递被词法拒绝的字符串，未打开任何设备。

POSIX 路径默认 ENOTSUP。只有主集成人员验证真实普通文件挂载、可信祖先目录、64 位 off_t、O_NOFOLLOW/O_NONBLOCK 后才能定义 MR_POSIX_TRUSTED_FILES。分支在 open 前 lstat 普通文件检查，并核对 open 后 dev/ino 和 fstat 普通文件。拒绝 /dev 路径，最后分量不跟随符号链接。尚未在 POSIX/NuttX 编译运行，主机 Windows 成功不可替代。

## 边界与失败语义

祖先目录必须受信任、不可被并发重定向；本候选不是面向恶意可写目录的路径沙箱。POSIX 的 lstat/open 间仍存在竞态，Windows 祖先 reparse 也未逐层固定。若不能确保目录信任，必须增加 mount-relative capability/openat 链路或拒绝接入，不应宣称阻止任意路径替换攻击。

每次操作前及完整读取后检查长度，可检测增长/截断；不保证发现同长度改写或先截断再恢复。模型存储必须在加载全程不可变。调用失败即关闭且置 fd=-1；read 错误时目标缓冲可能已部分改变，调用者必须丢弃整次结果。EINTR 总重试最多16次，短读继续，EOF和真实错误失败关闭；单次内核 read 卡住无法由此库终止，监督任务仍需超时策略。

close 不重试：部分平台 close(EINTR) 后描述符状态不确定，重试可能关闭被复用的描述符。close_error 保留原关闭错误，调用者必须按目标 libc 语义诊断；不能声称所有失败平台均已实际回收。注入关闭失败测试是先执行真实 _close 再返回模拟错误，仅验证报告/不重试逻辑。

没有 malloc/new、没有外部模拟后端。MR_TESTING 仅测试构建启用，故障注入包围真实主机 syscall；生产对象不含注入状态。

## 模型来源与哈希门禁设计（未实现设备 SHA）

可信 manifest 应包含：模型仓库及不可变 revision、精确 artifact 名、来源 URL、GGUF 量化规格、每分片长度与 SHA-256、总长度上限、审核记录。来源和期望 SHA 必须来自独立可信发布记录，不从待加载文件自行生成并当作期望值。当前未选择实际模型 artifact 或下载权重，因此不填造模型哈希。

部署时用现有已审计 SHA-256 实现（例如目标现有 mbedTLS SHA256 API，经主代理核对依赖版本及配置）流式处理同一 mr_file 句柄：open 精确长度 -> 64KiB read_exact 更新 SHA -> 比较完整32字节摘要 -> seek(0) -> 交付 loader。任何 hash/update/final/比较错误都 mr_close；不支持可靠哈希时拒绝 VERIFIED 状态。这里仅给出集成契约，当前 C API 未提供 hash_verified 标志，不能被称为已验证模型读取器。

验证期间及随后加载必须保持不可变挂载或等效写排除；同一句柄只避免路径替换，不能阻止同长度内容改写。分片逐一验签/哈希且校验聚合预算；GGUF tensor offset/size、维度乘法、metadata 分配预算仍由 loader 验证。CRC不是 SHA-256 替代品。输入/交付哈希使用 Python 标准库 hashlib，仅追踪本候选文件。

## 真实测试与复现

Windows MinGW gcc 12.2.0，C11 -Wall -Wextra -Werror -O2，生产对象与测试程序均编译。执行 run_tests.py；编译每步30秒、版本10秒、测试15秒。证据 evidence/host-tests.json 保留命令、退出码、输出及稀疏分配量。临时普通文件在本目录创建并自动清理，不创建或下载模型。

测试覆盖真实16字节文件/EOF零读取、长度不符关闭、偏移溢出/读取预算、注入 EOF/read/stat/seek/EINTR耗尽关闭恰好一次、注入 EINTR+短读恢复、关闭失败报告、真实打开期间截断、禁止路径词法拒绝。真实稀疏文件逻辑2147483775字节，物理65536字节（预算1MiB），验证2GiB之后 EDGE 标记和洞零值；先 FSCTL_SET_SPARSE 成功才扩展，不支持即 skip。设备节点、板端存储均未访问。

## 主代理集成输入

1. 实际 NuttX 配置/ABI：off_t/size_t/ssize_t 宽度、O_NOFOLLOW/O_NONBLOCK、lstat/fstat/lseek/read/close 的真实语义与挂载普通文件类型；目前只读 eMMC BCH 节点不能作为模型路径。
2. 授权的普通文件挂载点、不可变存储保证、实际模型精确来源/长度/SHA-256、分片策略，以及可靠 SHA 库版本。
3. 上游 loader 集成方案（包含 gguf_init_from_file 等旁路）；use_mmap=false/use_mlock=false 及对应编译能力门控仍需主代理处理。
4. 板端测试普通小文件/大文件能力、预算失败清理和加载前 hash 门禁；本交付不提供板端验证结论。

不涉及线程池、C++异常运行库、NEON、无线状态或硬件操作。由主代理负责选择集成及最终日志刷新。

# 流式模型完整性门禁 v1

这是独立主机候选，未接入正式 loader、NuttX 或任何模型文件。旧 parallel-model-reader-medium 文件保持不变；唯一新写入目录是 integrity-v1/。

## 行为

`mi_verify_open()` 消费调用者**已经打开的** `mr_file`，把所有权移入 `mi_model` 并将原对象置为关闭状态；整个流程不再使用路径，也不重新 open。初始化须使用 `MI_MODEL_INIT` / `MR_FILE_INIT`。对象不可复制，字段仅为无分配布局而公开，调用者不能绕过接口直接使用其 file；所有 API 须外部串行化，对象/缓冲区不得别名。

门禁检查精确预期长度以及 SHA-256 的64位比特计数上限（最多 UINT64_MAX/8 字节），要求 1..4096 字节调用者 scratch 且不超过 reader 的 max_read。先记录原偏移、seek(0)，分块 read_exact + 已有 SHA256，比较完整32字节预期摘要，最后恢复**原偏移**；只有恢复成功才进入 READY。初始偏移不自动归零，需要从头加载时调用 mi_seek(0)。测试以非零偏移证明恢复且 fd 不变。

`mi_read/mi_seek` 仅接受 READY；任何错误撤销状态并关闭句柄。验证失败同样关闭，没有可加载状态残留；底层已关闭时不重复 close，以保留 close_error。初始对象、关闭对象、失败对象均不可读。活跃门禁上再次验证返回 EBUSY，关闭原句柄及新传入句柄并撤销原 READY；请先 mi_close 后使用新的已打开句柄。close 不重试策略及真实 close(EINTR) 的平台限制继承 reader。

空模型沿用冻结 reader 的拒绝政策；没有绕过普通文件检查来伪造一个空打开句柄。SHA primitive 的标准空消息摘要单独测试通过。预期 SHA 必须来自可信固定模型清单，不能用待检查文件自行生成预期值。测试 fixture 的 Python hashlib 仅作为独立测试 oracle。

## 复用与输入

input/formal/ 是 app/k7agent/model_reader/model_reader.[ch] 的逐字快照，实际候选链接该快照；input/original/ 保存原冻结候选用于追溯，不参与构建。evidence/input-hashes.json 记录每个来源绝对路径、快照路径、字节数和 SHA256。

SHA256 逐字复用固定 llama b5046（74d4f5b041ad837153b0e90fc864b8290e01d8d5）examples/gguf-hash/deps/sha256/sha256.[ch]。原文件头声明：Igor Pavlov，2010-06-11，Public domain，基于 Wei Dai Crypto++ public-domain code。rotate-bits/package.json 明确 license 为 Public Domain。所有头部和 package.json 保留；未臆造其他来源、未下载代码、未自创 SHA 算法。

sha256_namespace.h + sha256_vendor.c 仅在预处理层把符号改为 mi_sha256_*，防止与正式无线 hostap sha256_* 冲突；vendor 文件不改。nm 审计只导出 mi_sha256_init/update/final/hash。该实现是已有实现复用和主机测试，不宣称密码学认证或完成独立安全审计。它无内存分配/外部服务，update/final 为 void，没有伪造可失败的返回值。

## 同句柄并不等于不可变内容

READY 表示这个句柄上完整读取的字节匹配预期摘要、长度检查和偏移恢复通过，不保证随后内容不变。同一已打开句柄避免“校验后按路径重新打开”问题，但不能阻止另一个写者修改同一文件。

底层 Windows reader 明确允许 FILE_SHARE_WRITE，POSIX reader 也未提供全局写排除。测试 scenario 15 在成功验证后真实同长度改写，随后读到新字节，作为**已观察限制**保存，不能被包装成防篡改通过。校验期间已经哈希过的字节也可能被修改而无法由本轮摘要发现。部署必须保证挂载不可变或等效排他写保护，覆盖验证到全部加载过程；否则拒绝把 READY 视为安全加载资格。文件哈希还不替代 GGUF 结构、offset/维度和内存预算验证。

## 主机证据和复现

运行 run_tests.py；gcc/每次子进程有超时（构建30秒，其余15秒），临时普通小文件仅在本目录创建并清理。最大 fixture 1,000,000 字节；不创建大稀疏文件、不访问模型/设备节点。

C11 -Wall -Wextra -Werror -O2 真实编译生产 reader/integrity/SHA 对象和测试 EXE。标准空串、abc、56字节标准消息、百万a以及55/56/63/64/65和4095/4096/4097/8192/8193边界通过；65字节 fixture 还覆盖1/63/64/65/4096读取块大小。Python hashlib 对所有 fixture 提供预期摘要。

故障测试覆盖摘要不符、真实待读内容改写、真实截断、读错误、fstat错误、初始seek错误、最终偏移恢复失败、参数/长度/bitcount越界、close错误保留、校验前不可读、校验后读/seek失败撤销、活跃对象重新验证关闭两句柄。MR_TESTING 与 MI_TESTING 只在测试构建使用，事件钩子让改写/截断发生在确定的读边界；文件变更是真实主机 I/O，读/stat/seek/close故障是明确注入，不能冒充 NuttX 自然故障。关闭失败注入先实际 close 再返回错误，用于验证报告和避免重复关闭。

evidence/host-tests.json 包含真实命令、超时、输出及返回码。-fstack-usage 仅为 MinGW 静态估计：mi_verify_open 自身240字节，不含调用链/调用者 scratch/中断开销，不可当作目标 NuttX 栈预算。实际 ARM64 编译、栈测量、挂载/写排除、可靠模型来源和 loader 消费同一所有权对象由主会话完成。正式文件/SDK/VM/硬件/中央日志均未操作。

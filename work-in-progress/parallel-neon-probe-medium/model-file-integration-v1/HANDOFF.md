# 只读U盘模型文件接入：同句柄边界与待取输入

本次交付是精确接入审查/最小接口契约及目标输入清单，**未生成虚构的完整loader补丁**。只读正式model_reader、B integrity-v1和固定b5046读文件路径；未访问U盘/SDK/设备、未下载模型、未改正式或B候选。当前没有真实模型文件，不能宣称模型读取/加载验收。

## 已确认与尚不能确认

| 项目 | 本地证据与结论 |
|---|---|
| MR_POSIX_TRUSTED_FILES | 正式model_reader.c显式门禁；未定义时POSIX mr_open在open前返回ENOTSUP。app/k7agent/CMakeLists目前只有注释，未启用Agent或该宏。不是由_FILE_OFFSET_BITS自动放行。 |
| O_NOFOLLOW/O_NONBLOCK | 冻结evidence/usb-storage-vfs-20260910/nuttx/include/fcntl.h:50/58均有定义。O_RDONLY为1<<0，**不是Linux的0**；只能用目标符号，不能复制Linux数值。 |
| nofollow实际处理 | 冻结fs/vfs/fs_open.c:151把O_NOFOLLOW传给SETUP_SEARCH，190检查desc.nofollow与INODE_IS_SOFTLINK并返回-ELOOP。mountpoint后续进入文件系统open路径，不能据此证明FAT内或中间路径有同样语义。 |
| off_t64 | neon-file64历史镜像记录off_t_bits=64；新增types.h明确CONFIG_FS_LARGEFILE选择int64_t off_t，否则int32_t。_FILE_OFFSET_BITS不控制该分支，仍需本次.config/编译断言。 |
| lstat/fstat | 新增冻结sys/stat.h声明lstat/fstat、S_ISREG及st_dev/st_ino/st_size字段，st_size为off_t。lstat调用nx_stat(resolve=0)，挂载FS无lstat时退回stat；fstat转交mount fstat。FAT身份字段语义仍未确认。 |
| O_NONBLOCK语义 | 宏存在不代表普通FAT文件/USB块读取有硬截止；需VFS→FAT→block路径返回/取消/超时约定。不承诺open/read一定在固定时间返回。 |

因此目前保留mr_open默认拒绝。A/B完成MSC/FAT不自动授权打开该宏；主代理核对下方输入后可只对该reader编译单元显式启用。

## 正式reader/integrity已经保留的保证

mr_open要求可信expected_length/max_length/max_read，POSIX拒绝/dev及/dev/前缀、检查lstat普通文件、open O_RDONLY|O_NOFOLLOW|O_NONBLOCK、fstat普通文件与前后st_dev/st_ino相同、长度精确且<=INT64_MAX，最后seek0。read/seek前后fstat复核长度，越界/短EOF/超过16次EINTR等失败关闭；partial output必须丢弃。close不重试EINTR，close_error单独保留。这不是免受USB移除或下层I/O阻塞的保证。

integrity-v1的mi_verify_open消耗**同一个**已打开mr_file并清空源owner，按可信SHA256验证全文件，成功恢复原absolute position才MI_READY；失败关闭且FAILED。必须先使mr_open返回position0，或验证成功后显式mi_seek(0)，才能从GGUF头开始。SHA匹配不是后续不可变性：要维持可信只读挂载/写排他直到所有模型读取结束。只读mount不能防范介质被其他主体重写；同尺寸内容更改不会被reader的长度检查发现。

路径仅做/dev字面前缀拒绝，未实现可信挂载根限制、规范化或中间组件身份锚定；例如非规范路径/父目录link仍依赖“可信祖先”契约。最终必须使用主代理配置的挂载根内固定模型文件白名单，拒绝模型输出提供的路径、..、空组件/别名、/dev块节点；不要为了尚未挂载而把设备节点作为模型文件。FAT的inode/dev若仅为常量，前后比较不等于一般Linux文件身份保证；挂载树与文件排他需要另证。

## 当前b5046必然丢失同句柄的路径

`src/llama-model-loader.cpp:470`调用gguf_init_from_file(fname)解析元数据；gguf.cpp:705内部ggml_fopen(fname,"rb")，调用gguf_init_from_file_impl(FILE*)后fclose。loader:478再new llama_file(fname,"rb")，llama-mmap.cpp:163再次ggml_fopen。分片模型在loader:529/546对每片重复该过程。

所以“先mr/mi验证fd，随后llama_load_model_from_file(原path)”**不是同句柄加载**。即使介质当前只读、路径可能稳定，也不能将重新open称为同fd承诺。/proc/self/fd路径同样是重开、并非已证实的NuttX设施，不作为绕过方案。

关闭mmap/mlock只减少映射路径，不消除上述二次open。非mmap tensor读取最终经files[idx]->seek/read_raw（loader:875/876、1030/1031及后续），当前llama_file底层用FILE*/fread/fseek/ftell；GGUF也直接fread和fseek/ftell，因此仅新增llama_file(fd)不足以覆盖元数据阶段。off_t64也不自动证明long/fseek/ftell宽度，当前代码显式long转换需单独核对。

## 最小可实施适配方向（尚未接线）

固定第一版只支持单文件GGUF，use_mmap=false、use_mlock=false，拒绝split_count>1。从open→verify→元数据解析→tensor加载只保留一个mi_model owner，永不暴露fd供另一路读取；每个阶段可seek回0但不能open第二次。

建议新增一个私有reader接口，只有read_exact、seek_absolute、tell、length和明确close-owner；read/seek均调用mi_read/mi_seek，tell/length应给integrity增加只读accessor（不能由外部直接篡改公开file字段）。大块tensor读取按已验证max_read切片，且整体offset+length先用差值检查。不要把当前FILE*直接fdopen后绕过mi位置/状态/长度检查：共享描述符位置会让mr_file.position失配，fclose还会与mi_close产生双owner。

需要把GGUF解析器的gguf_reader(FILE*)和header/alignment/data读取改为该reader；把llama_file/loader的单文件入口和非mmaptensor读取接入同一对象。metadata parser借用reader不关闭，完整loader owner在完成/失败后一次关闭；任何parser/分配/校验异常先销毁部分模型，再关闭句柄，close_error不得伪装成功。现有gguf_init_from_file_impl是内部FILE*接口，不是已提供的mi回调入口，不能只写一个转发声明声称完成。

该重构还需要gguf长度/数量/字符串内存上限和异常回收审核；SHA正确只证明与可信摘要相同，不替代GGUF结构与总内存预算。此轮没有实际模型/完整loader，故提供接线边界而不制造未经验证的目标实现。

## 给主代理的精准SDK只读取回清单

本代理不访问SDK；请主代理如需启用reader，取回这些**当前构建对应**文件/输出并保存哈希：

1. nuttx/include/sys/types.h、sys/stat.h、unistd.h、fcntl.h、nuttx/config.h或本次.config；确认off_t/st_size/long/size_t宽度、CONFIG_FS_LARGEFILE及lstat/fstat/lseek声明和_POSIX_C_SOURCE可见性。
2. VFS lstat/stat/fstat实现、inode路径搜索/SETUP_SEARCH实现、file_open/file_fstat/file_seek/file_read；不预设其具体文件名，先在SDK按函数符号定位，连同声明取回。
3. FAT挂载与file operations的open/stat/fstat/seek/read实现（由B的真实挂载候选定位），尤其st_dev/st_ino是否稳定、有无symlink、只读拒写和大offset错误码。
4. MSC/block读接口如何处理拔出、底层失败/超时和未完成I/O；O_NONBLOCK在此路径的实际意义。不要因为标志存在便承诺墙钟截止。
5. 当前目标只编译的shape探针：sizeof(off_t)>=8、sizeof(stat.st_size)>=8、sizeof(long)、lstat/fstat/open/read/lseek/close符号链接与定义来源；必须针对即将上板镜像，不套用neon-file64旧证据。
6. 后续主代理真实普通测试文件验证（本轮未执行）：只读可信挂载根、regular-file、长度/偏移边界/拒设备/错SHA关闭/验证后offset0/同fd全链路计数；不得用/dev/sdX或原始块读替代。无真实模型时只报告小文件I/O，不称模型通过。

## 交付证据

inputs.json逐文件SHA固定正式reader、integrity源、目标冻结fcntl/fs_open与历史off_t证据、固定loader/GGUF源码；未运行主机或目标测试。本次结论为代码路径审查和待取输入，不新增模型/文件IO成功记录。

## 新冻结VFS输入复核（覆盖早期待取状态）

已核对主代理新增model-file-vfs-inputs-20260910的10个文件及manifest哈希，见vfs-verification.json。sys/stat.h:181–183公开stat/lstat/fstat声明；unistd.h:389–390公开lseek(off_t)/read。fs_stat.c的lstat失败设置errno并返回-1，符合reader预期；内部file_fstat负errno由公开fstat包装转换。mountpoint身份/长度最终来自FS方法，仍需B的FAT stat/fstat实现。

fs_inodefind.c只是锁树、调用inode_search、加引用包装，并非inode_search实现；中间组件/软链接nofollow语义还缺实际inode_search实现与inode/inode.h的SETUP_SEARCH。不能把已取inode_find视为完成路径遍历审查。

新增输入消除了API声明与off_t配置开关这两项未知，但不消除FAT身份字段、只读可信根和loader二次open问题，MR_POSIX_TRUSTED_FILES仍不应自动开启。arena-provider真机小额成功属于内存证据，不替代文件门禁。早期checklist中已提供文件无需重复取回；只补本次config、inode_search、FAT与文件I/O路径及目标编译检查。

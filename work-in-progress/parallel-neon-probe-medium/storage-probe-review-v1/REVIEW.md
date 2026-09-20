# k7storage 只读源码与mock审查

已冻结app/k7storage四文件到input/，输入及三份已采集NuttX头SHA见inputs.json。只写本目录，未访问SDK/COM8/USB/设备、未改正式源码。测试编译调用的是原始k7storage_main.c正文，及仅修改list的候选正文，不是重写功能模型。

## 关键结论

1. **需修：list错误被吞。** 原list_usb_nodes不区分readdir EOF/错误，忽略closedir返回值，导致读取错误/close失败仍打印最终result=0。原源码mock明确复现此行为。list-errors.patch在每次readdir前清errno，NULL时检查errno，closedir失败传播非零；增加最多256个entry检查，达到上限保守返回-E2BIG（即使下一项可能是EOF）。返回错误时先前节点行仍可能已打印，最终command result才是完成门禁。
2. read在close_blockdriver之前打印repeated=1/CRC行；close失败最终result负数、main失败。不是未检查关闭，但验收器不能只看中间read行。候选不改这个输出协议，A应以同一命令最终result=0确认。
3. 未发现本应用显式写盘路径：没有write/ioctl写命令/mount/format，block open使用MS_RDONLY，geometry必须available且writeenabled=false，再且仅两次LBA0、nsectors=1。允许扇区512/1024/2048/4096，8KiB静态缓冲上界明确，输出CRC/签名不输出原始扇区内容。
4. 只读保证依赖真实MSC_READONLY驱动实现和rk3576_usbhost_initialize行为；宏门禁只证明编译配置请求，不证明底层没有额外命令。/dev/sd[a-z]名称不单独证明USB身份，README已要求主会话对应枚举证据。该工具不是普通模型文件reader，不能将raw /dev节点复用成模型。

## 目标API与尚缺输入

冻结fs.h的open_blockdriver(path,int mountflags,inode**) / close_blockdriver(inode*)及block read(inode,unsigned char*,blkcnt_t,unsigned int)→ssize_t与用法一致；read返回单位扇区，所以要求==1正确。冻结sys/mount.h的MS_RDONLY=O_RDONLY，冻结fcntl.h O_RDONLY=1<<0，mock采用此值，未套Linux常量。

新增冻结storage-types-inputs已确认struct geometry：bool三个字段、blkcnt_t geo_nsectors、blksize_t geo_sectorsize、geo_model[NAME_MAX+1]。已采types.h证明LARGEFILE时blkcnt_t=uint64_t（否则uint32_t）、blksize_t=int16_t；四种允许扇区均可表达，负sectorsize也被白名单拒绝，显式打印转换正确。mock已按uint64/int16补齐字段并重测负sector值，NAME_MAX只用mock值255。**仍不是完整目标编译**：还缺实际mutex/dirent依赖与完整目标配置，不声称mock struct大小等于目标ABI。

geometry≤0、writeenabled、错误sector size均在任何read前拒绝。若open_blockdriver成功却返回NULL inode，当前代码会解引用；这是依赖目标open成功合同，不通过mock任意伪返回NULL推断生产bug。回调NULL检查覆盖bops/geometry/read；负返回按原错误传播，短读/异常正数非1按-EIO，重复数据不一致-EILSEQ，每次成功open之后路径都调用一次close_blockdriver。close失败不无限重试。

nxmutex_unlock返回目前未检查；正常持有owner再解锁依赖mutex API合同，此项未模拟底层损坏/错误，不声称故障锁恢复通过。底层block read/start仍可能阻塞；有限次数不等于墙钟硬截止，不能为了超时强杀DMA使用者。list补丁限制条目数也不能保证每次readdir/printf不会阻塞。

## 测试与复现

`python run.py`先验证四份正式文件与冻结副本相同，再生成candidate.c/list-errors.patch，编译原源码和候选两个测试EXE（GCC C11 O2 Wall/Wextra/Werror），每子进程15秒。host-results.json与编号stdout/stderr保存命令、返回码、原始输出。四个编译/运行命令最终均0。

覆盖start成功/失败、非法read/list参数和节点路径、busy、list空/有节点/open失败/readdir失败/closedir失败、候选256项上界；四种扇区大小、block open失败、缺bops、geometry失败/不可用/可写/零扇区/超大扇区、首/次短读、负read错误、重复不一致与close失败。mock所有“设备”都是内存，read回调检查LBA0且nsectors=1；没有USB、宿主盘读写或目标驱动调用。原版对list错误预期为错误的成功返回，候选要求失败；其他条件保持相同结果。

复现脚本初次在Windows路径键分隔符上出现KeyError，尚未编译或调用测试；修为as_posix后完整测试通过。这是测试脚本问题，不是目标编译/设备失败。没有掩盖原list错误行为，证据中原/候选分别保留。

结论限于本应用控制流与已知API形状。未独立审计A/B驱动、未验收USB身份、介质安全、FAT、模型或目标运行；正式应用须主代理集成最小patch并编译验证。

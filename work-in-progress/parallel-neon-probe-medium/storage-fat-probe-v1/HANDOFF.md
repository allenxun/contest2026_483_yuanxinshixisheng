# 独立 k7fat 显式只读诊断

交付 `k7fat_main.c`，供 root 接入独立 app/k7fat 并配置构建项。未修改 k7storage、B候选、正式源码、SDK、设备或中央日志。首轮仅显式顺序运行 `k7fat mount`、`k7fat list`、`k7fat unmount`，不加载模型、不读取文件正文、不格式化、不创建磁盘目录。

必须同时启用 CONFIG_FAT_FORCE_READONLY、CONFIG_USBHOST_MSC_READONLY、CONFIG_FAT_FORCE_INDIRECT，否则编译#error。构建还需启用正常FAT/MSC依赖，由root独占配置。MS_RDONLY不能替代B的FAT只读核心：冻结VFS没有把mountflags传入FAT bind，原bind请求writeable=true。B的编译开关是全固件所有FAT挂载只读，不是单卷选项。

## 接口、状态与清理

- mount唯一源/dev/sda、目标/mnt/k7model、类型vfat、MS_RDONLY、data=NULL。拒绝任何额外参数；不启动USB、不自动探测其他设备、不自动重试。首次尝试前锁存attempted，即使失败或正常卸载也拒绝再次mount，需重新启动该诊断固件才能新一轮。该行为保守覆盖B原bind失败block-open清理缺口；A修复后可仍保留。
- list必须本命令此前mount成功。最多64个readdir返回项；到达64项即-E2BIG，不额外读取第65项，EOF恰在其后也保守报限额。名字扫描不超过sizeof(d_name)，没有NUL则-EILSEQ；最多打印64个原始名称字节的hex，控制符不会变成串口控制序列。长名标记truncated。无递归、stat、file open/read或自动正文输出。
- 每次成功opendir之后尝试一次closedir，包括readdir错误和达到上限。closedir错误锁存dir_uncertain并禁止后续list，避免重复积累可能未释放的DIR；不假定失败已经关闭，不自动重试closedir。可显式尝试普通unmount，由内核处理真实busy。
- unmount仅umount2(target,0)，不使用FORCE/DETACH/EXPIRE；失败不清mounted、不自动重试。EBUSY时保持挂载状态；其他错误mounted=1代表保守“未确认卸载”，不是证明内核仍挂载，因为冻结VFS在unbind之后也可能报错。未知状态应停止操作由主会话核对，禁止外部工具同时管理该挂载点。
- 单静态nxmutex_trylock owner串行命令。锁只覆盖本命令，不约束其他应用；验收期间必须独占/dev/sda与挂载点。没有强制终止线程/释放内核挂载结构。

VFS `fs_mount.c:487` 自己调用inode_reserve_path建立RAM伪挂载点；所以应用不mkdir仍可能出现RAM节点，这是mount语义，不是磁盘写入。该目标应在root RAM伪文件系统下，不能事先被其他文件系统/应用占用。候选不自动创建或清理目标父目录；若目标环境不接受路径则失败退出。`fs_mount.c:121`核定类型名称为vfat。冻结sys/mount.h核定mount与umount2签名、MS_RDONLY及flags0。

## FAT、扇区与读取界限

B的fs_fat32util.c:522起先读LBA0，检查FAT boot record；失败再迭代最多4个MBR主分区起始LBA。不要求另建/dev/sda1；这不是GPT、扩展分区链或exFAT支持保证。实际U盘仅已由主会话核定512字节扇区/60555264扇区与LBA0重复读取一致，尚不能由此确认可挂FAT或目录内容。

冻结MSC read-only代码接受512/1024/2048/4096扇区，并在read路径拒绝nsectors>4096/blocksize。FAT mount/cache/目录读取的本次审查调用为单扇区；fs_fat32.c直接文件读取分支会合并多扇区，因此本命令强制FORCE_INDIRECT，未来也不能仅靠文件read长度随意放大请求。它将普通文件读取经单扇区cache，不放宽MSC的4KiB上限。B的FAT头与5个候选源码、当前k7storage四文件、VFS/mount头与MSC全冻结，见inputs.json。

64项只是用户态枚举次数界限，不是墙钟时间上限：一次FAT readdir可能扫描长链/删除项、一次USB I/O仍取决于驱动超时；恶意损坏FAT/簇环尚未审计。不能在timeout后硬杀任务或强制卸载来冒充有界清理。本轮应使用已知用户介质、串口监督；出现卡顿停止后续命令，先核查内核状态。本命令不调用statfs/free-cluster全盘扫描。

## 真实主机测试与未验收项

本目录 `python run.py`，每子进程20秒。真实Windows MinGW GCC C11 Wall/Wextra/Werror/pedantic编译候选原C（仅把main重命名供调用），实际运行通过。原始命令/输出/退出码见test-output.txt，所有输入和输出有SHA256。覆盖无效参数、固定路径/flags、挂载失败不重试、成功列表、opendir/readdir/closedir错误、非NUL名字、64项边界、busy卸载保留、正常卸载后拒绝再挂、owner busy。

mock替代所有内核调用，DIR/d_name大小256为显式模拟，不是目标dirent.h ABI验证；本次已采集目录中没有真实dirent.h/nuttx mutex头，正式k7storage已使用对应接口但不代替目标编译。没有实际FAT镜像解析/USB/mount测试，不重跑或冒用B核心测试为本组件结果。待root目标编译核对头、静态全局在NuttX内建命令间的保持、A bind所有权修复及真实mount/list/unmount、卸载后无线恢复。目录名hex是实际名字的可逆表示，归档前由主会话按用户资料处理。

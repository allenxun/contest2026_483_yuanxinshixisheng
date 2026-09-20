# USB MSC 枚举与 FAT 只读接入清单

**最终范围：本轮只接 MSC 受限只读枚举/首扇区，FAT 留下一镜像。** msc-readonly.patch 是基于冻结 SDK 的两个文件候选：默认关闭 USBHOST_MSC_READONLY，启用后 write 在任何状态访问/USB提交之前 -EROFS，geometry=false。未应用到正式或 SDK。msc_read_checks.h 是单独、尚未接线的容量/READ10/CSW 检查 helper；不能因 helper 测试通过声称原 MSC 短包问题已修复。

当前不能把“打开 MSC/FAT 并传 MS_RDONLY”当成已经建立的介质拒写保证。冻结 MSC 有可用 WRITE10 路径、geometry 恒报可写；fat_bind 无条件调用 fat_mount(fs,true)。建议分为先枚举/有界块读，再接明确拒写的 FAT 挂载。本文只做本地审查与合成门禁测试，无 SDK 修改、无设备访问、无格式化或 U 盘写入。

## 最小配置和初始化

arena-provider-20260910/.config 已有 USBHOST、RK3576_USBHOST、RK3576_XHCI、HUB、WAITER（8192 栈）及 bulk 未禁用；MSC、FS_FAT 未开。本轮添加 USBHOST_MSC=y、候选 USBHOST_MSC_READONLY=y，保持 FS_FAT 未启用，保留 !DISABLE_MOUNTPOINT、SCHED_WORKQUEUE。MSC 代码要求 workqueue，枚举在 waiter 调用线程同步执行；其 class connect 的 TUR 最多100次、每次50ms，另有实际USB传输时间，不能把5秒当整个操作的硬上限。

在 rk3576_usbhost_initialize 的 g_lock 保护和 g_attempted 单次策略内，**xhci_initialize 启动 waiter 之前**注册 usbhost_msc_initialize；适当位置是 hub 初始化成功之后、xhci 初始化之前，并在失败时沿用现有失败返回/重启要求。应按 CONFIG_USBHOST_MSC 条件编译，检查返回值，不在每次命令重复注册同一静态 class registry。不要在设备已经枚举后才登记 class 并假定自动重绑定。

现有 k7host start 先注册自己的摄像头 g_registry，随后启动控制器。最小独立 storage-start 命令应只调用公共 USB 初始化，不走 camera/probe/stream/track 等入口；本轮不重做旧摄像头测试。主会话可选择新增独立小 app，或在 k7host 增加独立分支。本交付不改正式入口。

MSC 匹配 SCSI transparent / Bulk-Only（08/06/50），需 bulk IN/OUT 都存在，不是 UAS 驱动；LUN字段只支持现有代码所选逻辑单元，不宣称多LUN验收。成功后注册 /dev/sda…z，名称由实际枚举决定，不能假定 /dev/sda 永远是新插的 U 盘。记录 VID/PID、接口、容量、实际节点和新增前后差异。

## FAT、FSInfo 和拒写位置

冻结 fat_bind():2255 调 fat_mount(fs,true)，后者 util:498 拒绝 geo_writeenabled=false；bind 签名没有 mount flags 参数。补充精确 fs/mount/fs_mount.c:328 仅把 flags 传给 find_blockdriver（另一个分支传mtd_proxy），:453 bind 不传 flags，之后未存储 mountflags；fs_open 按每次调用 oflags 检查操作表，未见持久只读mount标志约束。fcntl.h 的 O_RDONLY=(1<<0)，不是 Linux 的0。故仅传 MS_RDONLY 不能让此 FAT 路径成为真正只读，不能绕过该缺口。本轮不修改 FAT/VFS。

正常 O_RDONLY read 不设置 FFBUFF_MODIFIED；close 调 fat_sync，但同步中的文件内容/目录时间/FSInfo 写回受 FFBUFF_MODIFIED 控制。fat_unbind 仅检查打开文件、关闭块驱动、释放内存，没有直接 flush/FSInfo 写回；MSC close 只管引用/销毁，没有 SYNCHRONIZE CACHE 命令。故没有从这些代码发现“每次正常只读 close/unmount 必然写盘”。这不是全路径零写保证。

fat_updatefsinfo 无只读标志判断，先 flush dirty cache，再在 FAT32 fs_fsidirty 时写 FSInfo。CONFIG_FAT_COMPUTE_FSINFO 会在挂载扫描后将 fs_fsidirty 置位；statfs 也可能触发空闲簇统计。首轮保持 FAT_COMPUTE_FSINFO=n，只做必要目录/文件读，避免全盘 statfs 扫描。即便关掉该配置，也不能替代底层拒写。FAT 对已有 FAT12/16/32 卷进行识别：先尝试整盘 boot sector，再扫描4个 MBR 主分区；这不构成 GPT/exFAT/NTFS 支持，识别失败即停止，禁止“修复”或格式化。

建议可审查的拒写方案（需主会话完成集成）：

1. 新增明确的 USBHOST_MSC_READONLY 配置，仅此实验启用。MSC write 入口在任何 CBW/传输前立即返回 -EROFS；geometry 报 false；当前 ioctl 默认 -ENOTTY，应保持不开放 passthrough/format/discard。不采用“只删应用写按钮”作为介质保护。
2. 解决 FAT 与真实只读 geometry 的兼容：取得精确 VFS flags 传递后实现对应 readonly mount，或引入明确的、实验固件全局 FAT read-only 配置，让 bind 使用 fat_mount(fs,false)，fat_hwwrite 也直接 -EROFS，并拒绝 FAT 所有修改操作。后者影响该固件全部 FAT 卷，需列明范围，不能悄悄全局改 false 却仍宣称普通读写挂载完整可用。
3. 暂不建议以 geometry 继续谎报 true 掩盖 bind 不兼容；若主会话仅为一次有限读取选择“write 永远拒绝但 geometry true”的隔离方案，必须明确这是兼容权宜、不是正确的只读 geometry，并仍保证低层拒写。首选先补清晰的只读语义。
4. 通过模拟 block_operations 的 write 计数测试挂载、readdir、文件读、close、正常 umount：期望底层写调用0；对故意写请求在纯主机假设备验证 -EROFS 且 USB传输调用0。不要为了负例验证对用户真实 U 盘发 WRITE10。真实运行仅记录拒写/提交计数，不通过实际写入检验。

## 同步、长度、DMA 与读取可靠性

MSC read/write 使用 priv->lock 覆盖 CBW→数据→CSW，能防本 class 同设备事务交织；xHCI endpoint exclsem 覆盖等待，controller lock 不跨等待。不可绕过 class 直接分别提交阶段。read 的 -EAGAIN 重试没有次数上限，枚举成功不保证后续读取有界；首次读取仍需主会话外部截止/失败恢复，不能超时后立即释放可能 DMA 使用的内存。

现有 READ CAPACITY10 将 last_lba+1 存 uint32、blocklen 存 uint16；last_lba=0xffffffff 会溢出，超大扇区会截断。必须在缩窄前拒绝不支持容量/扇区尺寸。READ10 仅32位LBA、16位count，当前 readcbw 未验证范围而直接编码；初轮限制合法512/1024/2048/4096扇区与每请求≤4096字节，之后按主会话需要放宽，不把全部可读文件直接一次提交。FAT_FORCE_INDIRECT=y 可让首次FAT数据读通过单扇区缓存，降低批量和用户缓冲区复杂度；FAT_DMAMEMORY 需要板端 fat_dma_alloc/free 实现，当前未证实，不应仅打开配置就认为DMA正确。

现有 read 接受 CBW/data/CSW 的任意非负返回，仅校验 CSW status，最后返回完整 nsectors；缺严格短传输、CSW signature/tag/residue 检查。不能以 read 返回成功证明内容完整。接入前宜补精确长度和CSW校验（包括容量/inquiry初始化阶段）；故障后需要正确BOT恢复，不能盲目当下一正常事务继续。首次实际内容应与用户已有文件的可信哈希对照，否则只算读到数据。

板端 dmacapable 仅允许 CONFIG_RAM_START..START+SIZE：当前 0x40400000..0x48200000（末端不含）。模型 arena 不应当作直接 USB DMA 区。xHCI 对不可达或不满足整cacheline条件的buffer分配 kmm_memalign bounce，IN前/后 invalidate，OUT clean，复制回在调用线程完成；因此已有端到端 bounce 支持向普通有效 CPU modelarena 缓冲读回，并不需要仅因地址不直接DMA可达再新增reader复制层。bounce自身的可达性依赖 kmm 的分配范围，函数未再次调用 dmacapable 检查，须保持系统heap原范围。不能扩大RAM或模型池范围来规避这项边界。

xhci_normal_setup 按物理64KiB边界切TRB，64KiB是单段边界，不是整个request必然上限；它受 XHCI_TD_MAX/TRB容量限制。初轮≤4KiB请求最多跨2个64KiB段，避免把大模型缓冲直接提交。地址范围、cacheline、bounce内存、USB2 Bulk枚举与实际介质响应仍需目标验证。仅主机算法测试不证明 cache/DMA 正确。

## 本地门禁与剩余工作

read_gate.py 是待集成策略的离线模型，校验范围、长度、READ10、CBW/CSW完整性；test_read_gate.py 的20个案例全部为合成（正常边界、短包、tag/signature/residue/status、越界/截断、WRITE10拒绝）。它没有修改或测试真实驱动。真实transaction JSON若由主会话采集后送验，还需另证记录完整性；没有trace就不输出零写结论。

本轮门禁：拒写候选评审与目标编译；实际生成config和MSC入口链接检查；确认注册先于枚举；geometry=false；对真实新节点仅首扇区/≤4KiB读、记录精确传输和内容，不挂载。read检查helper还需接入原class路径，特别容量缩窄前校验、数据传输长度检查、BOT失败恢复。后续FAT独立镜像再做全局只读编译选项或可传递的只读mount语义以及fat_hwwrite防漏。本交付没有应用补丁或完成设备验收。

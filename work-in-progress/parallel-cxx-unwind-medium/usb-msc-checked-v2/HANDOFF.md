# Checked read-only MSC v2

候选已把容量、READ10范围和BOT完整性检查接入冻结的真实 usbhost_storage.c；仅 CONFIG_USBHOST_MSC_READONLY=y 启用整套受限路径，默认n保留旧行为。candidate.patch 是针对最初冻结SDK两个文件的完整补丁，**取代v1，不要叠加应用在已打v1的文件上**。candidate/下是可直接审查的完整候选文件。主代理负责与实际SDK差异协调、编译和设备验证。

## 行为与所有权

- write 在访问inode/class或USB提交前返回 -EROFS；geometry=false。打开已闭锁实例失败；已有fd后续read/geometry也失败。关闭仍沿用原引用计数/物理断开路径，没有把bot_failed伪装成disconnected，没有主动注销、强杀任务或释放DMA。
- 首次诊断只接受512/1024/2048/4096逻辑扇区，每次READ10最多4096字节，验证负LBA/32位编码范围、容量边界、非零16位count；参数错误不提交USB且不污染BOT状态。容量在last_lba+1及uint16缩窄**之前**检查，拒绝READ CAPACITY16哨兵和不支持的扇区大小。
- TUR、REQUEST SENSE、READ CAPACITY10、INQUIRY、READ10均经usbhost_checked_command。CBW必须恰31字节，数据必须恰预期长度，CSW必须恰13字节且签名/tag/residue/status符合。长度短路判断在字段读取前；tag在共享tbuffer被数据或CSW覆写前存局部变量，且每个CBW递增tag。容量响应放8字节局部数组，经已有xHCI bounce读取，CSW仍留tbuffer供旧初始化控制流检查。
- 完整有效的TUR status=1、residue=0仍可代表命令尚未就绪，沿原有限100轮/50ms等待与REQUEST SENSE逻辑继续。status=2、无效status、任何其它命令status!=0以及短传输、CSW字段错误、负transport返回均锁定bot_failed。不是通用BOT恢复实现，兼容性比普通MSC更保守。
- checked事务对EAGAIN**零次重试**：任意阶段可能部分提交，不重新发CBW。第一次失败返回-EIO并标记需重新枚举；后续命令不再DRVR_TRANSFER。该标记仅由新class实例memset清零，不能用重复open或命令重置它。有效TUR轮询不同于失败BOT序列盲重试。

## xHCI 返回语义与未覆盖接口

正式xHCI的xhci_transfer_wait成功返回epinfo->xfrd，xhci_transfer保留此字节数，并在返回前执行DMA finish/copyback，因此bulk精确长度比较有依据。已有endpoint锁与class读锁串行化事务；connect初始化发生在实例公布为块设备前。没有加第二层reader拷贝或扩大DMA地址域。

控制传输xhci_ctrl_xfer却把非负返回归一为OK。GET_MAX_LUN不能从DRVR_CTRLIN的返回值检查真实收到1字节，本候选仅保留合法stall(-EPERM)单LUN回退，其它控制错误锁定失败并从initvolume的既有引用清理段退出；不冒称GET_MAX_LUN精确长度已验证。若后续需要该项保证，必须由HCD接口或控制完成证据单独解决。该请求仍只使用LUN0，不宣称多LUN支持。

xhci_ioc_wait使用nxsem_wait_uninterruptible但可因任务取消返回错误；本候选没有改变HCD取消、endpoint停机或其DMA释放逻辑。**不得强杀正在transfer的任务来满足外部截止，也不能仅由class的bot_failed证明DMA已停止。** 不响应时由主会话按已有控制器/整机恢复方案处理；重枚举是否需要物理断连或整机重启取决于实际端点恢复路径。本候选不发BOT reset来假装修复失步。

## 主机证据

运行 `python -B verify.py`：从完整候选按函数定义提取25个实际函数（含checked函数、CBW编码、初始化命令、read/write/geometry），原样编译进mock-replay.c，以显式模拟ABI/传输回放。不是重写一个平行算法作为被测对象。run-evidence.json记录每个提取函数行号/hash、完整命令/输出、输入与候选哈希。mock-prefix.h只是宿主ABI脚手架，不是SDK头文件；目标结构布局和整个TU构建尚未验证。

严格C11 `-Wall -Wextra -Werror -pedantic -O2` 编译通过；31组回放通过：正常/4KiB/最后边界，超限无提交，CBW/data/CSW短包，签名/tag/residue/status，EAGAIN阶段停止，失败后read/geometry拒绝，容量溢出/缩窄，初始化命令、共享缓冲tag覆写，以及write无提交。正常TUR status=1保留，phase error关闭。测试中的所有设备/响应为mock，不是用户U盘证据。

默认关闭分支使用相同去头文件预处理环境与冻结原始源码比较，非空白记号一致；这证明该配置下源码分支保留，不能替代实际NuttX编译。对冻结副本git apply --check通过，未应用。早期主机首次编译因提取列表漏getle16/getbe16失败，补全后通过，failed-run.json保留原始错误；曾用空白split比较产生断行误报，改为记号比较后通过，未据此修改默认逻辑。

## 接入门禁与范围

主会话需核对两文件原哈希再集成（若已有v1应评审替换差异）、检查实际生成CONFIG_USBHOST_MSC_READONLY=y和完整TU编译，保持MSC初始化先于xhci waiter、只读块读入口独立于摄像头。确认目标反汇编write无USB提交，实际read对应checked路径，设备geometry=false，再做受限首扇区/块读。真实原始数据、BOT状态、VID/PID/节点/容量、镜像哈希由主会话记录。

FAT/VFS、模型文件reader、介质写入、格式化、摄像头测试均不在本候选内。没有SDK/VM/网络/设备访问、没有正式文件修改。缺完整目标编译、真实USB枚举/传输和失败恢复验证；不能凭mock通过宣称U盘已接入或可以挂载。

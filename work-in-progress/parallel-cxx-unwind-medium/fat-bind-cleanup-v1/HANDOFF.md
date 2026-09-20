# FAT bind failure cleanup

确认B的fat-readonly-v1候选继承了原有漏close：fat_bind成功调用块驱动open后，fs_heap_zalloc失败直接返回；fat_mount失败只销毁mutex/释放fs，也直接返回。VFS fs_mount.c:453调用bind，失败分支仅回退之前额外增加的inode引用并走inode_release，没有调用块驱动close；成功bind后若挂载点创建失败才走unbind。这是两类独立所有权，不能把inode引用回退当成块驱动close。

cleanup.patch仅修改fat_bind，基于B候选candidate/fat/fs_fat32.c，需先集成B FAT只读候选再应用本补丁。opened只在可选open回调存在且成功后设true；分配失败保存-ENOMEM，fat_mount失败保留其原始ret，统一errout_with_open在close回调存在时恰调用一次并忽略close返回，不掩盖主要失败。open失败仍保持原先返回-ENODEV，未扩改其错误映射。没有成功open或没有close回调时不伪造close。

成功bind仍转移fs/块驱动open给成功挂载，补丁不提前close、不增加/减少inode引用，也不改fat_unbind。正常unmount及VFS成功bind后的回退仍只调用现有unbind一次close。打开文件导致unbind=-EBUSY时保留挂载/打开资源，再正常unbind时才关闭。没有修改B/C目录、正式源码、SDK或设备。

## 可复现验证

运行 `python -B verify.py`。从真实B候选提取fat_mount，从本补丁后候选提取fat_bind/fat_unbind，保持函数体原样；test.c把它们编译到mock块驱动/分配器/boot parser环境，run-evidence.json记录提取hash、输入hash和完整命令/输出。不是用另写的bind模型替代实际函数。

19条路径在FAT默认/强制只读、O0/O2共4个组合通过：fs分配、geometry、扇区buffer分配、boot sector读、boot格式识别、FSInfo检查失败各配合close成功/失败，均恰一次close、保留主要错误、无分配/mutex残留、输出handle未污染。另测open失败、空inode、可选open/close缺省、正常bind/unbind、busy-unbind后正常释放、成功bind后VFS式unbind回退。VFS引用数以mock哨兵核对FAT函数不自行修改；未编译执行整个VFS。

严格C11 -Wall -Wextra -Werror -pedantic，仅关闭原函数未用参数警告（fat_bind的data等），无其它宽松编译。补丁对冻结B副本git apply --check通过，未应用。mock的geometry/读/boot/FSInfo返回明确注入的错误，测试范围是清理所有权，不能算真实文件系统识别或USB介质验收。

目标完整构建与实际失败恢复由主会话集成后完成。本任务没有扩大到FAT其它操作、VFS引用算法或全盘安全审计；USB失败停止和只读行为沿用各自候选边界。

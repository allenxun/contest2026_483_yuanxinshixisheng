# checked CSW debug 最小修复

冻结正式MSC原文件SHA256：0fdaaccfee3f36c03a82b66e718e14d759976d071a0b29963173adb48a6f273f。

checked-csw-debug.patch仅在usbhost_checked_command成功返回之前增加已有usbhost_dumpcsw调用；不修改默认非checked分支、返回值、传输参数、只读门禁或失败状态。

调用在nbytes==USBMSC_CSW_SIZEOF且signature/tag/residue/status所有条件通过之后；失败if先短路检查长度并return，因此新增dump不会先于长度验证读取。已有dump只读signature/tag/residue/status，均在13字节CSW内。allow_not_ready许可status1时该字段也按原规则通过，不改变判断。

CONFIG_DEBUG_USB和CONFIG_DEBUG_INFO同时启用时函数声明/定义存在，新调用消除checked-only配置下defined-but-unused。任一未启用时原有宏`#define usbhost_dumpcsw(csw);`把调用展开为空语句；源调用的分号形成合法双空语句，参数不求值。不需另加条件编译，不压低-Werror、不改函数可见性。

仅只读静态审核与补丁生成，未访问SDK/硬件、未执行完整目标编译。主代理应应用后按原USB独立配置重编译验证。候选/原文件/patch哈希见hashes.json。

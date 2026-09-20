# 语音 Session 哈希循环定位

实际 trace ELF 的 memset 来自 lib_bsdmemset.c。PID11 保存寄存器重复采样 PC=4079cffc、4051df20、4051df38，位于 Abseil 插入查找/探测推进循环。读取表容量1、控制字节 1e ff 1e ff ff ff ff ff 80，未找到空槽。

实际 memset 组装机器字前未将 int c 转换为 unsigned char；Abseil ResetCtrl 使用 int8_t(-128) 表示空槽。最小修复先截取低8位再复制到机器字。主机使用原函数体和64位字/8字节对齐 shim，覆盖8种填充值、8种偏移、0..96长度、返回值和边界保护：原版O0/O2各6208项中2736失败，修复版各0失败。不是ARM64真机验收。

补丁：port/patches/libc-memset-byte-normalization.patch。候选及主机结果：work-in-progress/memset-byte-fix。严格核对原文件后已应用到SDK，并独立构建voice-memset-fix-20260911；尚未上板。当前运行trace镜像保持原行为，不宣称ASR或语音配网完成。此前主机测试首轮遇MinGW UNALIGNED宏重定义，测试shim增加undef后编译通过，未改实际函数逻辑规避测试。


最新真机覆盖：voice-memset-fix-20260911 编译、ELF/MMU及异常表检查通过，BIN SHA256 8cf15cd2c372427063b9a2027418ec7d0de09cc60b139c0feb1a6a975bb2e667。OTG传输1.0279秒，双地址CRC d0c66f0c，RAM启动后真实Add Session/Run/cleanup通过，输出11,22,33,44。ASR模型未运行，无线回归尚未执行，不宣称语音配网完成。

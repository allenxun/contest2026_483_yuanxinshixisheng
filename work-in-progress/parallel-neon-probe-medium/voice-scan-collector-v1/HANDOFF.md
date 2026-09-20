# 固定扫描结果收集器

`scan_collector.c/h` 是独立纯C11组件，不分配、不记录日志、没有密码字段、不访问硬件、不建立broker或锁。全部调用和读取由外部同一串行化机制保护，初始化仅在发布前执行。候选尚未接入正式代码。

固定64项，原始SSID最多32字节，可以为空、含NUL或非UTF8；尾部未用SSID字节归零。按6字节BSSID去重。更强RSSI将SSID、安全类型、信道、band、RSSI等整条记录替换；相同或更弱RSSI保持旧记录。容量满后遇到新BSSID返回SC_FULL并锁存truncated，但已有BSSID更强更新仍允许。正式prov_scan_report旧实现只换scan字段而保留旧security；该函数所在源文件逐字冻结于input，SHA256见inputs.json。

状态严格：init→IDLE，非零且严格增加的generation才能begin；COLLECTING时禁止重新begin。accept/freeze/cancel先核对generation，再核对COLLECTING。freeze后本generation不允许任何写入，包括cancel；cancel只在收集时清空全部记录/count/truncated，保留generation墓碑及CANCELLED状态。FROZEN/CANCELLED可在调用者释放快照读者并证明旧worker/RX已静止后，以更高generation重新begin；UINT64_MAX后无可用下一代，禁止回绕。重复freeze/cancel不是成功幂等操作，返回SC_STATE。失败/忽略操作保持状态内容，SC_FULL只改truncated。

generation只绑定本地槽，不证明固件报告来源；调用者不能把旧帧重新标成新generation后依赖本组件识别。仍需统一服务仲裁、worker退出及STOP/CLOSE/RX排空证据。component不验证SSID可发音、BSSID合法性或信道监管合法性；已解码记录仍检查security0..3、band0..1、channel非零及SSID长度。结构体仅进程内使用，不可按sizeof直接发送线缆或持久化（有ABI padding/字节序）。

本目录执行 `python run.py`。真实Windows MinGW GCC在O0/O2均以C11、Wall/Wextra/Werror/pedantic编译运行通过，原始输出在test-output.txt。测试覆盖完整安全字段替换、32字节二进制SSID/空SSID、非法长度与字段、同/弱RSSI忽略、64/65项、满容量更新、旧generation、冻结后拒写、cancel清空、generation溢出、空指针。固定实例主机sizeof=2960字节，以实际日志为准；目标ABI待编译，不把主机大小当目标保证。

未执行ARM交叉编译、并发测试或真实列表采集。外部串行化是明确前置条件，内部没有线程安全实现。接入测试还需在唯一WiFi服务覆盖BLE/语音/连接争用与迟到帧；不能把本地收集器通过当作无线扫描端到端验收。仅本目录写入，正式/SDK/设备/中央日志均未修改。

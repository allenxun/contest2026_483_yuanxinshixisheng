# Robot tool dispatcher 候选交接

仅主机纯软件候选，未集成、未上板。唯一开发目录为本目录。没有硬件、COM8、BLE、摄像头、USB、执行机构、STM32、eMMC、SDK、Ubuntu、模型、凭据或网络调用；没有提交推送、修改其他候选或中央 logs。

可核实身份：协作子代理 `/root/robot_tools`，由 `/root` 分派，所属可见父任务上下文 `01a0892e-2964-7ec3-bd76-9ab4937980cb`。工具未提供该子代理独立原生会话 UUID，因此不编造；本文不是原生 JSONL 日志。日志采集及官方校验由协调者处理。

## 接口与能力

`include/dispatcher.hpp` 是 C++17 单头文件，固定 8 个槽位，无动态容器、I/O、工作线程或 backend 回调。`validate()` 接收类型化 Request，只返回验证后的请求或明确错误。原始文本/JSON/模型输出解析不在范围内。`Dispatcher::submit()` 自身再次校验，不能通过伪造 Validated 绕过。Tool 白名单只有 Capabilities、WifiStatus；两者也只产生供未来可信适配层处理的只读调用描述 `Call`，本候选没有设备适配层。

- Capabilities 返回的是**候选接入能力**，不是固件所有能力：queryValidation=true、deviceAdapterBound=false、actuatorsEnabled=false。真实硬件能力未知，不能根据这份静态信息宣称设备可执行。
- WifiStatus 依据正式 `app/k7radio/prov_service.inc` status 路径存在；connected 必须来自服务确认认证及 DHCP/IP ready，不能来自L2关联、请求接受或模型文本。示例仅用 FakeBackend 注入合成状态；不存在实际查询。地址检查拒零、127/8、169.254/16、组播和保留高地址；只检查局部合法性，不证明 DHCP、网关或互联网成功。断开状态要求全零地址。不处理子网广播判定，未来适配层须提供真实有效服务快照。
- GimbalTarget 验证后恒返回 Disabled，没有可启用开关。采用 `app/gimbal/gimbal_link.c:gimbal_link_adopt` x[-800,800]、y[-120,1030] 作为保守候选请求范围；同文件 `gimbal_link_pack` 的 y[-200,1030] 是线编码范围，二者保持区别，未改原接口。`gimbal_link_send` 成功仅为成功入队，不是测量位置或 MCU ACK；现有协议没有可用事务 ACK，不能推导动作 completed。
- Photo、WifiScan、WifiConnect及未知枚举均 Unsupported。正式拍照/无线功能存在不等于本候选已经接入。原生仪器识别未接入，无此工具。没有访问其他代理的新候选。

## 状态、事务及取消契约

Requested 仅表示纯校验通过；Accepted 表示**本地账本接纳**，不是设备接纳。take()只取一次调用描述，仍是Accepted。可信DeviceEvent Started才转Running；只有同owner/id/tool的Completed事件及匹配载荷才转Completed，并要求已Running。Failed事件、超时和时钟倒退转Failed；cancel()转Cancelled，只取消对只读结果的兴趣，不停止或断开任何物理设备。超时与取消后的结果被丢弃。deadline同刻到期优先，时钟倒退永久拒新请求。

owner非零；ID在Dispatcher生命周期全局递增，不循环，UINT64_MAX后Exhausted。不同owner不可查询/取消对应记录；终态release才能复用槽位，ID不复用。TTL 1..30000ms，差值运算避免截止时间加法溢出。销毁并重建Dispatcher属于新进程会话，调用者必须先隔离/清空旧事件通道；没有跨重启防重放承诺。

所有方法必须由同一序列化协调线程调用。DeviceEvent是可信适配层入口，不是安全进程边界：任意本进程C++调用者都能构造，因此严禁把不可信文本直接转为事件。没有执行动作的backend资源，本候选无需也不能证明物理取消/释放。未来若加动作必须另审明确的设备ACK、取消栅栏与静默确认后释放，不能沿用本地只读取消作为动作停止。

VoiceLink继续拥有唤醒/密码/语音状态机及ASR/TTS资源编排。本候选未实现TaskPort、不重造WifiPort/broker。`TaskPort::handle()`的字符串返回契约与类型化事件账本不一致，需协调者明确适配：不能将请求已接受的字符串当作设备完成。正式WiFi共享事务接口尚未接入。

## 验证与复现

在本目录运行：

```powershell
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/run.py
```

MinGW G++12.2，C++17、Wall/Wextra/Werror/pedantic，O0/O2各6073检查通过；最终证据 `evidence/20260910T065837965270Z/result.json`。编译各60秒、测试各10秒上限；argv、实际退出码、耗时、stdout/stderr原始字节均保存。覆盖状态顺序、错误参数、禁用/未接入、伪造owner/tool、重复/迟到、取出前完成、取消、deadline同刻、时钟倒退、容量、ID耗尽、时间溢出、2000轮取消/释放及陈旧结果。

前一版本O0/O2各6069通过，保留在 `evidence/20260910T065812907466Z`；新增IPv4拒绝边界后重新验证。没有编译/测试失败或超时；初始只读检索两次把PowerShell通配符作为rg路径，返回路径错误，随后用显式目录完成读取，该检索错误不是测试失败或设备结果。

输入按路径复制并SHA256固定在 `inputs.json`、`input/`，是本次读取快照，不是对仍可能由主任务更新的文件作长期一致性承诺。`delivery.json`列交付文件哈希；其自身哈希由 `delivery.sha256` 提供，避免自引用。

未完成：真实查询适配器、真实事件认证/顺序通道、TaskPort桥接、文本/JSON解析、openvela编译、设备回归、动作ACK协议与授权策略。无语言模型或语音整体功能验收。本目录交付后冻结，后续修订需保留独立版本及真实验证。

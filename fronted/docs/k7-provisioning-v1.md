# VelaVision K7 Android 配网对接

> 历史说明：当前设备联调改为信息接收回执，不执行真正联网。请以 [k7-credentials-receipt.md](k7-credentials-receipt.md) 为准；下文 connect 提交和猜测的联网结果事件不再由当前页面调用。

依据：D:/download/记录/前端对接说明.html，协议 v1 / id36，2026-09-09。
修改位置：养肤设备 → openVela → OpenVelaConnectActivity。
K7Protocol / K7ProvisioningClient 专用实现，不修改其他护理设备的 BleManager 指令通道。

## 已接入
- 按 VelaVision K7 名称或广播中的配网服务 UUID 发现设备；无名称首包也可识别。
- 服务 6b7a0001-78c3-4f2e-9c2f-3ecbc2d74680。
- 写命令 6b7a0002-78c3-4f2e-9c2f-3ecbc2d74680，仅 Write With Response。
- 通知 6b7a0003-78c3-4f2e-9c2f-3ecbc2d74680，每次连接重新订阅 CCCD。
- 能力读取 6b7a0004-78c3-4f2e-9c2f-3ecbc2d74680，检查 v=1、encrypted=true、busy=false 后报告就绪。
- 初始化等待超时最多重试2次（总3次），间隔1、2秒；不重放业务命令和密码。
- 扫描发送大写 ASCII X (0x58)，一个独立字节、不加LF。
- 普通JSON命令以LF结束、最多512字节，固定不超过20字节分片，逐片等待写回调。
- 单事务串行；扫描60秒、状态15秒；连接结果暂定60秒；半包10秒超时。
- scan_started绑定id，ap汇总，scan_done先校验原始count，再按原始SSID Base64/频段/security去重及信号排序；提示truncated。
- 中文跨包完整解码，非UTF-8和隐藏SSID保持标识；隐藏网络无SSID可提交，显示但不提交空标识。
- 断开、失败、取消、退出时取消事务、销毁GATT、清空分片；敏感数据不记录日志。

## 密码提交及新增固件结果约定（待实际返回格式联调）
固件必须在能力中返回 connect:true，才允许弹窗提交；false保持扫描功能并说明未开放联网。
提交的UTF-8 JSON示例（末尾追加LF）：

    {"v":1,"id":103,"cmd":"connect","ssid_b64":"TGFuc2Vl","password":"用户输入的密码"}

SSID使用扫描返回的原始Base64，不能从显示名称重新编码。
示例ID由App在1–65535内生成，设备应回传相同id。

建议成功终止事件：

    {"v":1,"id":103,"event":"connect_result","wifi_connected":true,"ip":"192.168.1.100","session":31}

中央适配同时识别 connect_result / connect_done / connected / wifi_connected / status；
这些名字是为后续固件预留的兼容约定，不是宣称id36文档已经定义了它们。
无论事件名，都必须匹配事务id、v=1；有session时必须匹配本次连接。
只有 wifi_connected:true 且 IP 有效才提示成功，不接受纯文本1/ok或单独code:0作为成功。
IP获取成功不代表互联网可达，界面仅提示Wi-Fi连接成功和地址。

进度事件支持 connect_started / connecting / wifi_connecting / authenticating / dhcp；
不会因进度事件结束事务。失败使用 event:error、code，例如 not_ready、auth_failed、dhcp_timeout。
没有IP的终止事件会提示失败/未获取IP，保留列表供重试，不自动重发密码。

## 验证
- 全项目隔离Kotlin类型检查通过（临时资源符号fixture，不等于APK构建）。
- 27项JUnit通过，其中K7协议12项：JSONL中文分包、多个消息、ID/行数验证、原始SSID、频段、密码转义、512字节限制、能力版本和成功判定。
- 尚未对目标手机和新版固件进行实机测试；现有id36固件不支持真正密码认证/DHCP。
- 正式Android构建受本地SDK 36.1缺失影响。需真机验收配对、旧绑定恢复、后台/锁屏、断连及真实Wi-Fi成功/失败。

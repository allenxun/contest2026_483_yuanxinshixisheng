# K7 真实联网：当前前端配置
依据：2026-09-14《K7 前端交接：蓝牙配网与联网成功回报》，并与当前 App 实现对照。
当前页面已改用 connectWifi() / cmd:connect，不再调用 submitCredentials()。

发送：UTF-8 JSON，末尾LF，逐包最多20字节、有响应串行写。
示例：{"v":1,"id":103,"cmd":"connect","ssid_b64":"TGFuc2Vl","password":"实际密码"}

能力：须 connect:true 且加密、通知已就绪。
服务发现后若系统尚未配对，App先发起系统配对并等待完成，再写Notify CCCD。配对最多等待60秒；订阅及能力读取最多15秒。已配对但返回认证/加密错误时，提示用户在系统蓝牙设置中取消旧配对后重试。
接收：
- wifi_connecting：更新等待提示，不结束事务、不重置总超时。
- wifi_connected：必须匹配v/id/当前session，必须包含wifi_connected:true和有效非零IPv4；不接受IPv6或缺失成功标志。
- error：读取code/detail；诊断只记录受限错误码及数字detail，不记录任意详情或密码。
- credentials_received：不能当作联网成功，提示确认新固件。

联网等待120秒；wifi_connecting不重置总超时。密码规则为8..63个可打印ASCII字符，不trim；当前不支持开放网络空密码。
每次蓝牙就绪后先发status。用户刷新Wi-Fi列表时再次先查status；已联网则展示真实IP，不发送X、不自动断网。未联网才发送X，扫描最多60秒。
BLE断开、联网等待超时或成功通知丢失时，页面标记为未知。重连、订阅并读取新session后发status恢复，不自动重发密码。
status和联网成功均只表示局域网已取得IP，不代表DNS、互联网或云语音可用。stored:false明确提示断电后需重新配网。
板端本地“联网成功”播报不由App触发；当前无播报完成事件，须现场听音验收。
其他护理设备不变。
旧信息接收能力/协议解析保留兼容代码，但当前页面没有回退到信息接收模式。

验证：K7协议、配网客户端和实际配网页隔离Kotlin类型检查通过；23项K7 JUnit通过，覆盖严格成功字段、IPv4、session、status恢复和120秒/60秒时限。
类型检查使用本机缓存依赖和资源符号fixture，不代替APK构建。尚未完成新版固件、手机和本地播报闭环实测。

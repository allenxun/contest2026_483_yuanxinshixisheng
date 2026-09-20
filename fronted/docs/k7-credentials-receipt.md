# K7 Wi-Fi 信息接收联调（当前有效）
依据：D:/download/记录/接入示例.mjs 与 前端蓝牙联调操作手册.md，2026-09-09。
本文件取代 k7-provisioning-v1.md 中关于真实联网提交及猜测结果事件的部分。

## 流程
搜索 VelaVision K7 → 发现指定服务、订阅通知、确认加密 →
用户点击获取 Wi-Fi 列表（ASCII X）→ 完整 scan_done 后选择网络 →
输入密码 → 发送给设备 → 匹配回执后显示“OK，设备已收到”。

- 能力使用 receive_credentials:true 控制提交；缺失或false时禁止提交并提示确认固件版本。
- connect:false 只表示未开放真正联网，不影响信息接收能力。
- 用户密码保持原样，必须8..63个可打印ASCII字符（0x20..0x7e），包含首尾空格也不trim。
- SSID必须规范Base64、原始长度1..32字节，使用扫描原始ssid_b64。
- 提交UTF-8 JSON加LF，最多512字节，每片最多20字节、Write With Response串行发送。
- 同一时间一个事务，提交回执等待15秒；扫描仍为60秒。

提交示例（仅测试密码）：
    {"v":1,"id":103,"cmd":"submit_credentials","ssid_b64":"TGFuc2Vl","password":"EXAMPLE_ONLY_123"}

必须匹配的回执：
    {"v":1,"id":103,"session":25,"event":"credentials_received","validated":true,"stored":false,"wifi_connected":false,"ip":null}

成功条件：v=1、id为当前提交编号、session为当前链路会话，且上述布尔字段和ip均匹配。
不把裸OK、GATT写成功、status或旧connect事件当作信息接收成功。
界面显示“OK，设备已收到 / 信息未保存，尚未联网”。不宣称密码正确或已经连接路由器。
invalid_password表示格式不合法；invalid_ssid提示重新扫描。超时/断开显示未确认收到，不自动重放密码。
输入框在提交/关闭时清空、禁止自动填充和保存状态，密码不写日志或本地存储。

## 验证
隔离全项目Kotlin类型检查通过，32项相关JUnit通过（K7协议17项+已有15项）。
正式APK构建、目标Android手机配对及真实板端接收回执仍需现场验证；
本机Android SDK 36.1不完整，隔离类型检查不替代资源链接或APK构建。

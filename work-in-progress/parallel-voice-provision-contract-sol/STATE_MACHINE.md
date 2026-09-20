# 状态迁移

| 当前状态 | 可信输入/事件 | 下一状态 | 动作 |
| --- | --- | --- | --- |
| WaitingWake / Idle | 精确唤醒词 | Scanning | 固定问候；申请 VOICE 扫描事务 |
| Scanning | 同 ticket Ready snapshot | ChoosingNetwork | 去重、按 RSSI 排序、最多播报五项 |
| ChoosingNetwork | 有效编号 | EnteringPassword | 保存候选索引；只播报 SSID |
| EnteringPassword | 单字符词 | EnteringPassword | 追加一字符；只播报累计长度 |
| EnteringPassword | 完成且长度合法 | ConfirmingPassword | 播报长度并要求“确认提交” |
| ConfirmingPassword | 非确认文本 | ConfirmingPassword | 明确提示尚未提交 |
| ConfirmingPassword | 否/重新输入 | EnteringPassword | 擦除全部密码 |
| ConfirmingPassword | 确认/确认提交 | CredentialsAccepted | 唯一允许调用 `submitCredentials` 的迁移；随即擦除本地副本 |
| CredentialsAccepted | 同事务 Wpa2Authenticating | AuthenticatingWpa2 | 如实播报正在认证 |
| AuthenticatingWpa2 | 同事务 Wpa2Authenticated | AcquiringDhcp | 如实播报认证成功并等待地址 |
| AcquiringDhcp | 同事务 DhcpAcquiring | AcquiringDhcp | 如实播报正在获取地址 |
| 任一连接态 | 同事务 IpReady + 有效 IPv4 | Completed | 如实播报成功和地址 |
| 任一可交互/运行态 | 取消 | Idle | 取消本事务、擦除密码 |
| EnteringPassword | WrongPassword | EnteringPassword | 擦除密码后重输 |
| 连接态 | NetworkNotFound | ChoosingNetwork | 清除选择，保留扫描列表 |
| 扫描/输入/连接态 | 对应期限届满 | Idle | 超时优先于同一 `poll()` 的成功事件 |
| 任一状态 | 契约破坏/无效 IP/一般失败 | Error | 取消本事务并擦除密码 |

不同 request ID、取消后的迟到事件和终态后的事件不改变状态。开放网络仍需口头确认，确认后以长度零提交。扫描结果中的 SSID 必须先由无线适配器验证为无控制字符的 UTF-8；状态机不把 ASR 文本当作 SSID 或事务标识。

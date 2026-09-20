# openVela 新页面接口对接（2026-09-13）

范围：仅“我的 → openVela 测肤列表 → 人员 → 报告列表 → 报告 → 护肤方案”。
旧登录、旧报告/方案、养肤设备里的 K7 配网逻辑不变。

## 已实现
- 独立服务地址 http://10.3.3.170:18085；2026-09-14起改为OpenVelaAuth独立加密会话，不读取原TokenManager。
- 入口未登录或会话过期时打开OpenVelaLoginActivity。POST /api/v1/auth/sms-challenges取得challengeId，再POST /api/v1/auth/sessions登录；成功回到人员列表。
- 手机号自动补中国区号；验证码由用户输入，不内置固定账号/密码。installationId在本安装持久化，安装绑定材料目前提交空对象（已实测开发后端接受）。Token过期/401重新登录；403仅提示权限不足，不退出旧系统登录。
- GET /api/v1/me/member-access-grants：20条游标分页，按 memberId 去重。
- GET /api/v1/members/{memberId}/skin-reports：20条游标分页。
- GET /api/v1/skin-reports/{reportId}?view=full：真实指标、说明和图片。
- GET /api/v1/members/{memberId}/care-plans?reportId=…&limit=2：要求恰好一个方案，不随意选择第一条。
- GET /api/v1/care-plans/{planId}?view=full：方案正文、步骤及内嵌 progress；等待/生成/失败状态支持手动刷新。
- 新流程不再引用 mock 人员、报告分数、护理步骤。无数据、无授权、失败分别提示。
- 同源媒体携带原 Token；外部 HTTPS 图片不携带 Token，不自动跟随重定向。媒体禁用内存/磁盘缓存。
- 页面销毁取消请求；刷新取消旧请求；结果回调校验原登录 Token 未变。
- 沿用蓝牙连接/订阅与停止、查询、退出确认保护。正式开始工作按钮暂不可用，不把原占位 b 指令当服务端准入成功。

## 字段兼容与未确认事项
1. 最新运行文档的 MemberAccessGrantListItem 仍只有 grantId/memberId/grantedAt。按产品要求兼容接口的 name/memberName/displayName、avatarUrl/avatar/faceImageUrl（支持 member 对象）。字段最终名称需后端确认；缺姓名显示“未返回姓名”，缺头像用默认头像。
2. SkinReportImage 文档只有 mediaId/contentUrl，不定义视角。仅在明确返回 view/angle=left/front/right 时映射三视图；未标视角的图显示为独立结果图片，不按数组顺序猜测。缺视角使用带“示例图”标识的默认图；有URL但加载失败显示失败/重试。
3. 新登录已做HTTP实测：用户指定测试账号取得challengeId、会话Token，并成功读取成员授权列表，目前items为空。需准备真实授权数据才能继续报告链。refreshToken暂不存储、不自动刷新，到期明确要求重新登录。
4. 开始护理还缺设备ID/能力协议和人脸准入采集约定。本次不创建 care-executions、不自动上报 observation 或 closure。已有停止查询按钮仅属于原BLE占位联调协议，不能宣称是后端执行闭环。
5. 内网服务为 HTTP，network security config 只放行10.3.3.170，其他主机仍禁止明文。上线必须提供正式HTTPS服务地址。
6. 详情采用接口内嵌progress，未做自动轮询，避免后台持续请求。累计执行后的进度刷新应在执行闭环接入时补齐。

## 验证
- 当前新流程全部 Kotlin 源码及共享图片预览代码：隔离类型检查通过（依赖本机缓存及编译资源符号，不是APK构建）。
- OpenVelaDataTest：10项JUnit测试通过，包括缺列表拒绝、成员不匹配拒绝、真实姓名头像、默认头像、无假分数、视角不猜测、就绪方案缺正文拒绝及字符串计数。
- 标准 Gradle :app:compileDebugKotlin --offline：被本机 SDK android-36.1 平台不完整阻塞。
- 2026-09-14新短信登录HTTP链已验证成功，返回Bearer会话；授权成员为0。正式APK安装及真机新登录页面联调尚未完成。

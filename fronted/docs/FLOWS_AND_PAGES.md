# AISIA 系统流程与页面开发文档

> 本文档基于当前代码实际跳转关系梳理，描述 AISIA Android 应用的业务流程、页面（Activity / Fragment）清单及导航关系。
> 代码路径均相对于 `app/src/main/java/com/example/aisia/`。

---

## 一、概述

AISIA 是一款美容护肤 Android 应用，提供智能测肤、3D 人脸模型、蓝牙 / WiFi 设备连接、皮肤报告分析、护肤方案与护理等功能。

| 项目 | 说明 |
|------|------|
| 技术栈 | Kotlin + AppCompatActivity/Fragment + OkHttp + Coil + CameraX + Android BLE |
| 应用入口 | `SplashActivity`（LAUNCHER）→ `MainActivity`（底部导航主框架） |
| 主框架结构 | `MainActivity` 通过 BottomNavigationView 承载 4 个 Tab，hide/show 方式切换 Fragment |
| 登录态管理 | `TokenManager` 存取 Token；`HttpHelper` 全局拦截 401（清 Token + 跳登录页） |
| 合规要求 | 首次启动由 `PrivacyManager` 弹出隐私政策弹窗，同意前不初始化功能页面 |
| 页面规模 | 29 个 Activity + 4 个 Fragment |

---

## 二、页面清单

### 2.1 启动与主框架

| 页面名称 | 类名 | 路径 | 说明 |
|----------|------|------|------|
| 启动页 | `SplashActivity` | `SplashActivity.kt` | LAUNCHER 入口，显示 2 秒后无动画跳转主框架 |
| 主框架页 | `MainActivity` | `MainActivity.kt` | 底部导航容器，支持 `EXTRA_TAB`（home/scan/skincare/mine）指定启动 Tab |

### 2.2 底部导航 Tab（Fragment）

| Tab 名称 | 类名 | 路径 | 说明 |
|----------|------|------|------|
| 首页 | `HomeFragment` | `ui/home/HomeFragment.kt` | 轮播图（自动滚动 3s）、智能测肤卡片、连接设备卡片（区分有/无数据两种样式） |
| 咨询 | `ScanFragment` | `ui/scan/ScanFragment.kt` | 智能聊天：文字输入 / 长按语音录音（16kHz WAV）→ ASR 识别（`/api/asr/recognize`）→ 发送消息，含热门问题卡片与打字机动画 |
| 养肤 | `SkincareFragment` | `ui/skincare/SkincareFragment.kt` | 设备卡片：微晶 / 小超炮 / LED（蓝牙搜索连接）+ 摄像头（WiFi 测肤） |
| 我的 | `MineFragment` | `ui/mine/MineFragment.kt` | 头像/昵称/手机号（`/api/user/profile`）、测肤历史、设备历史、3D 模型入口 |

### 2.3 功能页面（Activity）

| 模块 | 页面名称 | 类名 | 路径 |
|------|----------|------|------|
| 登录账户 | 登录/注册页 | `LoginActivity` | `ui/login/LoginActivity.kt` |
| 登录账户 | 个人中心页 | `ProfileActivity` | `ui/mine/ProfileActivity.kt` |
| 登录账户 | 资料编辑页 | `ProfileEditActivity` | `ui/mine/ProfileEditActivity.kt` |
| 智能测肤 | 测肤功能选择页 | `SkinListActivity` | `ui/skintest/SkinListActivity.kt` |
| 智能测肤 | 智能测肤页 | `SmartSkinTestActivity` | `ui/skintest/SmartSkinTestActivity.kt` |
| 智能测肤 | 3D 人脸模型页 | `Scan3DActivity` | `ui/skintest/Scan3DActivity.kt` |
| 智能测肤 | 脸型/颜值结果页 | `FaceResultActivity` | `ui/skintest/FaceResultActivity.kt` |
| 智能测肤 | 皮肤分析选择页（遗留） | `SkinAnalysisActivity` | `ui/skintest/SkinAnalysisActivity.kt` |
| 智能测肤 | 设备测肤页（遗留） | `SkinTestActivity` | `ui/skintest/SkinTestActivity.kt` |
| 报告方案 | 肤质检测报告页 | `SkinReportActivity` | `ui/report/SkinReportActivity.kt` |
| 报告方案 | 智能 分析页（遗留） | `AiAnalysisActivity` | `ui/ai/AiAnalysisActivity.kt` |
| 报告方案 | 护肤方案页 | `SolutionActivity` | `ui/solution/SolutionActivity.kt` |
| 报告方案 | 护理执行页 | `WorkActivity` | `ui/work/WorkActivity.kt` |
| 测肤历史 | 测肤历史页 | `SkinHistoryActivity` | `ui/skinhistory/SkinHistoryActivity.kt` |
| 测肤历史 | 报告列表页 | `ReportListActivity` | `ui/skinhistory/ReportListActivity.kt` |
| 测肤历史 | 报告对比页 | `ReportCompareActivity` | `ui/skinhistory/ReportCompareActivity.kt` |
| 设备 | 蓝牙设备连接页（无入口） | `DeviceConnectionActivity` | `ui/device/DeviceConnectionActivity.kt` |
| 设备 | WiFi 摄像头测肤页 | `DeviceSkinTestActivity` | `ui/device/DeviceSkinTestActivity.kt` |
| 设备历史 | 设备历史页 | `DeviceHistoryActivity` | `ui/devicehistory/DeviceHistoryActivity.kt` |
| 设备历史 | 历史方案列表页 | `HistoryPlanActivity` | `ui/devicehistory/HistoryPlanActivity.kt` |
| 设备历史 | 方案详情页 | `PlanDetailActivity` | `ui/devicehistory/PlanDetailActivity.kt` |
| 3D 模型 | 3D 模型列表页 | `Model3DListActivity` | `ui/model3d/Model3DListActivity.kt` |
| 3D 模型 | 3D 报告列表页 | `Model3DReportListActivity` | `ui/model3d/Model3DReportListActivity.kt` |
| 智能咨询 | 智能 对话咨询页 | `AiConsultActivity` | `ui/consult/AiConsultActivity.kt` |
| 智能咨询 | 在线咨询页 | `OnlineConsultActivity` | `ui/consult/OnlineConsultActivity.kt` |
| 护理预约 | 护理项目详情页 | `ProjectDetailActivity` | `ui/skincare/ProjectDetailActivity.kt` |
| 护理预约 | 护肤推荐页（无入口） | `RecommendActivity` | `ui/recommend/RecommendActivity.kt` |

---

## 三、业务流程详解

### 流程 1：启动流程

```
SplashActivity ──2 秒──▶ [首次启动：隐私政策弹窗] ──同意──▶ MainActivity
```

1. `SplashActivity` 为 LAUNCHER 入口，显示 2 秒；
2. 首次启动时 `MainActivity.onCreate` 中由 `PrivacyManager.ensureAgreed()` 弹出隐私政策弹窗，用户同意前不初始化功能页面（不申请敏感权限、不收集个人信息）；
3. 同意后初始化底部导航并进入默认 Tab（首页）。

### 流程 2：主框架（4 个底部 Tab）

`MainActivity` 通过 BottomNavigationView 切换 4 个 Fragment（hide/show + commitNow）：

| Tab | Fragment | 主要内容 |
|-----|----------|----------|
| 首页 | `HomeFragment` | 轮播图、智能测肤卡片、连接设备卡片；根据接口数据区分"功能卡片"与"数据卡片"两种样式 |
| 咨询 | `ScanFragment` | 智能聊天界面：热门问题、文字输入、长按语音（ASR 转文字后自动发送） |
| 养肤 | `SkincareFragment` | 设备卡片：微晶、小超炮、LED、摄像头 |
| 我的 | `MineFragment` | 用户资料、测肤历史、设备历史、3D 模型入口 |

- 支持通过 `MainActivity.EXTRA_TAB`（"home" / "scan" / "skincare" / "mine"）指定启动 Tab，`onNewIntent` 中同样处理；
- 首页"连接设备"卡片点击后切换到养肤 Tab（不再直接进设备连接页）。

### 流程 3：登录/注册流程

```
[未登录点头像 / 任意接口 401] ──▶ LoginActivity ──登录/注册成功──▶ MainActivity(home)
                                    └──返回按钮──▶ MainActivity(mine)
```

1. `LoginActivity`：手机号 + 短信验证码，支持登录与注册（`/api/auth/app/sms/send`、`/api/auth/app/sms/login`，免 Token 白名单接口）；
2. 成功后延迟 2 秒跳转 `MainActivity`（home Tab）并 finish；
3. 401 场景由 `HttpHelper` 全局统一处理：清除 Token → `FLAG_ACTIVITY_NEW_TASK | CLEAR_TASK` 跳转登录页（2 秒去重防抖）；
4. 返回按钮回到 `MainActivity`（mine Tab，`CLEAR_TOP | SINGLE_TOP`）。

### 流程 4：智能测肤流程（核心）

```
HomeFragment 测肤卡片 ──▶ SkinListActivity ──选择功能──▶ SmartSkinTestActivity
                                                            │ 拍照 → 上传 OSS → 智能 分析
                              ┌─────────────────────────────┼─────────────────────────────┐
                              ▼ type=skin                   ▼ type=3d                     ▼ type=face
                     SkinReportActivity              Scan3DActivity                FaceResultActivity
                     （肤质检测报告）                 （3D 人脸模型）                （脸型/颜值结果 → 返回首页）
```

1. `SkinListActivity`：三张功能卡片——肤质检测（type=skin）、3D 人脸模型生成（type=3d）、人脸检测（type=face）；
2. `SmartSkinTestActivity`：状态机 PREVIEW → CAPTURED → ANALYZING → COMPLETE，CameraX 预览拍照、TTS 语音引导人脸位置、图片上传 OSS 获得 `oss_key`；
3. 按 type 分流并携带 `oss_key`：
   - skin → `SkinReportActivity`（调用肤质分析接口生成报告）
   - 3d → `Scan3DActivity`（WebView 展示 3D 模型，网络请求经 JS Bridge 走原生 OkHttp）
   - face → `FaceResultActivity`（颜值/脸型分析结果，底部浮动返回按钮回首页）
4. 其他入口：`SkinHistoryActivity`、`ReportListActivity`、`Model3DListActivity`、`Model3DReportListActivity` 的"添加"按钮也会进入 `SmartSkinTestActivity`。

### 流程 5：报告 → 方案 → 护理流程

```
SkinReportActivity ──生成方案──▶ SolutionActivity ──"去护理"──▶ WorkActivity ──返回首页──▶ MainActivity
```

1. `SkinReportActivity`：肤质检测报告展示（支持 reportId / oss_key 两种进入方式，硬件加速开启）；
2. `SolutionActivity`：护肤方案页，图片全屏预览、建议项切换选中；
3. `WorkActivity`：护理执行页（加载 `/api/my-device/{device_id}/treatment-plans/{planId}`），"返回首页"清栈回 `MainActivity`。

### 流程 6：测肤历史流程

```
MineFragment ──▶ SkinHistoryActivity（测肤人列表）
                    ├── 点击人员 ──▶ ReportListActivity（报告列表）
                    │                   ├── 点击报告 ──▶ SkinReportActivity（报告详情）
                    │                   ├── 勾选两份报告 ──▶ ReportCompareActivity（报告对比）
                    │                   └── 生成方案 ──▶ SolutionActivity
                    └── 添加按钮 ──▶ SmartSkinTestActivity（携带 id/deviceId）
```

1. `SkinHistoryActivity`：按设备展示测肤人员列表，携带 `id`、`deviceId`、`deviceName`、`deviceType` 进入；
2. `ReportListActivity`：某位测肤人的报告列表（携带 `faceId`、`faceNickname`）；
3. `ReportCompareActivity`：A/B 两份报告同屏对比（`reportIdA` / `reportIdB`）。

### 流程 7：设备连接流程（蓝牙 / WiFi）

```
SkincareFragment 设备卡片（微晶/小超炮/LED）
    ──▶ 蓝牙搜索 BottomSheet（按名称关键字过滤 "EVE AISIA"）
    ──▶ "连接中"波纹弹窗 ──连接成功──▶ 保存设备到服务器
    ──▶ SkinHistoryActivity（携带 id / deviceId / deviceName / deviceType）

摄像头卡片 ──▶ DeviceSkinTestActivity（WiFi 摄像头测肤：SDP 配置、拍照保存、水分值读取）
```

1. 设备卡片配置（`DeviceCardConfig`）：id、标题、蓝牙名称过滤关键字、引导页路径；
2. BLE 扫描使用 `BluetoothLeScanner`，权限经 `PrivacyManager` 同意后申请；
3. 连接成功后先调接口保存/查询历史设备获得服务端 `device_id`，再跳转 `SkinHistoryActivity`；
4. `DeviceSkinTestActivity` 走 WiFi 摄像头（WifiCamera SDK）：创建 SDP 文件、取流拍照保存到相册、读取水分值，可跳转系统 WiFi 设置。

### 流程 8：设备历史流程

```
MineFragment ──▶ DeviceHistoryActivity ──点击设备──▶ HistoryPlanActivity ──点击方案──▶ PlanDetailActivity ──返回首页──▶ MainActivity
```

1. `DeviceHistoryActivity`：历史设备列表；
2. `HistoryPlanActivity`：该设备的历史护理方案列表（携带 `EXTRA_DEVICE_ID`）；
3. `PlanDetailActivity`：方案详情（`EXTRA_DEVICE_ID` + `EXTRA_PLAN_ID`，接口 `/api/my-device/{device_id}/treatment-plans/{planId}`），"返回首页"使用 `NEW_TASK | CLEAR_TASK` 清栈。

### 流程 9：3D 模型流程

```
MineFragment ──▶ Model3DListActivity（3D 人脸列表）
                    ├── 点击人员 ──▶ Model3DReportListActivity（3D 报告列表）
                    │                   ├── 点击记录 ──▶ Scan3DActivity（task_id + 3dType=list 查看模型）
                    │                   ├── 查看报告 ──▶ SkinReportActivity（reportId）
                    │                   └── 生成方案 ──▶ SolutionActivity（失败时回退到报告页）
                    └── 添加按钮 ──▶ SmartSkinTestActivity（type=3d）
```

1. `Model3DListActivity`：调用 `/api/3d/faces`（可按 deviceId 筛选）加载人脸列表；
2. `Model3DReportListActivity`：报告列表，支持与测肤历史一致的"生成方案"逻辑（`setClassName` 跳转 `SolutionActivity`，找不到时回退报告页）。

### 流程 10：个人中心流程

```
MineFragment 头像 ──已登录──▶ ProfileActivity ──"修改资料"──▶ ProfileEditActivity ──保存──▶ 返回
                  └──未登录──▶ LoginActivity
```

1. `MineFragment` 通过 `TokenManager.isLoggedIn()` 判断登录态；
2. `ProfileActivity`：GET `/api/user/profile` 加载资料（昵称、手机号脱敏、头像、生日、地区）；
3. `ProfileEditActivity`：编辑并 PUT `/api/user/profile` 保存。

### 流程 11：智能咨询 / 分析流程

1. 咨询 Tab `ScanFragment`：文字 / 长按语音（AudioRecord 16kHz WAV → `/api/asr/recognize`）→ 发送消息 → 打字机动画回复；上滑超过阈值取消发送；
2. `SkinAnalysisActivity`（遗留选择页）：肤质检测 / 3D 模型 / 人脸检测三卡片 → `AiConsultActivity`（携带 type，调用 `/api/chat/completions` 对话补全）；
3. `SkinTestActivity`（遗留设备测肤页）→ `AiAnalysisActivity`（智能 分析，标题行可展开收起）→ "查看报告" → `SkinReportActivity`。

### 流程 12：推荐 → 预约 → 在线咨询流程

```
RecommendActivity ──"查看项目"──▶ ProjectDetailActivity ──"立即预约"──▶ OnlineConsultActivity
（护肤推荐/避坑提醒）              （项目信息/护理步骤/选美容师）          （在线咨询聊天）
```

### 流程 13：当前无活跃入口的页面（遗留 / 待接入）

| 页面 | 状态说明 |
|------|----------|
| `DeviceConnectionActivity` | 蓝牙设备连接页，已注册但无页面跳转它（原首页设备卡片已改为切换养肤 Tab） |
| `SkinAnalysisActivity` | 遗留选择页，可跳 AiConsultActivity，但无外部入口 |
| `SkinTestActivity` | 遗留设备测肤页，可跳 AiAnalysisActivity，但无外部入口 |
| `AiAnalysisActivity` | 仅被 SkinTestActivity 打开 |
| `RecommendActivity` | 仅被注册，无页面跳转到它（自身可跳 ProjectDetailActivity） |
| `MineFragment` "护理"入口 | 代码中已被注释隐藏（恢复时解开 `layoutCare` 注释并显示图标） |

---

## 四、页面导航总览图

```
SplashActivity（启动页）
    │
    ▼
MainActivity（主框架，底部 4 Tab）
 ├── HomeFragment（首页）
 │    ├── 测肤卡片 ──────────────▶ SkinListActivity ──▶ SmartSkinTestActivity
 │    └── 设备卡片 ──▶ 切换到养肤 Tab
 │
 ├── ScanFragment（咨询）：智能聊天 + 语音 ASR
 │
 ├── SkincareFragment（养肤）
 │    ├── 微晶/小超炮/LED ──▶ 蓝牙搜索弹窗 ──▶ 连接 ──▶ SkinHistoryActivity
 │    └── 摄像头 ──▶ DeviceSkinTestActivity
 │
 └── MineFragment（我的）
      ├── 头像 ──已登录──▶ ProfileActivity ──▶ ProfileEditActivity
      │         └──未登录──▶ LoginActivity ──▶ MainActivity(home)
      ├── 测肤历史 ──▶ SkinHistoryActivity ──▶ ReportListActivity
      │                                          ├──▶ SkinReportActivity ──▶ SolutionActivity ──▶ WorkActivity
      │                                          ├──▶ ReportCompareActivity
      │                                          └──▶ SolutionActivity
      ├── 设备历史 ──▶ DeviceHistoryActivity ──▶ HistoryPlanActivity ──▶ PlanDetailActivity
      └── 3D 模型 ──▶ Model3DListActivity ──▶ Model3DReportListActivity
                                                ├──▶ Scan3DActivity
                                                ├──▶ SkinReportActivity
                                                └──▶ SolutionActivity

SmartSkinTestActivity 分流：
 ├── type=skin ──▶ SkinReportActivity
 ├── type=3d  ──▶ Scan3DActivity
 └── type=face ──▶ FaceResultActivity ──▶ MainActivity

遗留链路（无外部入口）：
 SkinAnalysisActivity ──▶ AiConsultActivity
 SkinTestActivity ──▶ AiAnalysisActivity ──▶ SkinReportActivity
 RecommendActivity ──▶ ProjectDetailActivity ──▶ OnlineConsultActivity
 DeviceConnectionActivity（孤立）
```

---

## 五、关键技术要点

| 要点 | 说明 |
|------|------|
| Tab 定向跳转 | 各页面通过 `MainActivity.EXTRA_TAB` + `FLAG_ACTIVITY_CLEAR_TOP \| SINGLE_TOP` 回到指定 Tab；`PlanDetailActivity` 等"返回首页"使用 `NEW_TASK \| CLEAR_TASK` 清栈（对齐小程序 switchTab 行为） |
| 401 全局处理 | `HttpHelper` 拦截 401：清 Token → 跳 `LoginActivity`（2 秒去重），业务页面无需单独处理 |
| 隐私合规 | `PrivacyManager.ensureAgreed()` 首启弹窗，同意前不初始化功能、不申请敏感权限 |
| 权限清单 | 蓝牙（BLUETOOTH_SCAN/CONNECT、定位）、相机、录音、网络/WiFi（NEARBY_WIFI_DEVICES） |
| 测肤状态机 | `SmartSkinTestActivity`：PREVIEW → CAPTURED → ANALYZING → COMPLETE → 按 type 分流 |
| 隐式跳转兜底 | `SolutionActivity`、`WorkActivity` 通过 `setClassName` 跳转并 try-catch，找不到时回退报告页或提示"开发中" |
| FileProvider | `${applicationId}.fileprovider`，路径配置见 `res/xml/file_paths.xml` |

---

## 六、文档信息

- 依据代码：`AndroidManifest.xml`（29 个 Activity 注册）+ 各页面 `startActivity` 实际跳转代码逐一核对
- 相关文档：`docs/ARCHITECTURE.md`（架构）、`docs/API_REFERENCE.md`（接口）
- 注意：`docs/ARCHITECTURE.md` 中"首页设备卡片 → DeviceConnectionActivity"已过时，当前实现为切换到养肤 Tab
- 文档生成时间：2026-08-07

# Aisia Android 应用总体流程图

> 依据当前工作区代码生成，更新时间：2026-08-21。  
> 范围：页面功能、用户交互、Activity/Fragment 跳转、关键接口与异常回退。  
> 说明：实线表示当前可达流程；虚线表示隐藏、旧版或暂无直接入口的页面。

## 1. 应用总体导航

```mermaid
flowchart TD
    A["启动 App"] --> B["SplashActivity<br/>启动页停留约 2 秒"]
    B --> C["MainActivity"]
    C --> D{"是否已同意隐私政策"}
    D -- "否" --> E["隐私政策弹窗"]
    E -- "同意" --> F["初始化四个底部页面"]
    E -- "未同意" --> E
    D -- "是" --> F

    F --> H["首页<br/>HomeFragment"]
    F --> Q["小远测肤 / 智能咨询<br/>ScanFragment"]
    F --> K["小信养肤<br/>SkincareFragment"]
    F --> M["我的<br/>MineFragment"]

    H --> H1["轮播图<br/>自动轮播 / 手势切换"]
    H --> H2["测肤卡片<br/>肤质检测 / 结果评分 / 重新测肤"]
    H --> H3["设备卡片<br/>连接设备 / 重新连接"]
    H2 --> SL["SkinListActivity<br/>肌肤智能检测"]
    H3 --> K

    Q --> Q1["热门问题"]
    Q --> Q2["键盘输入"]
    Q --> Q3["按住说话"]
    Q1 --> CHAT["SSE 连续会话"]
    Q2 --> CHAT
    Q3 --> ASR["语音识别"] --> CHAT

    K --> K1["微晶"]
    K --> K2["小超炮"]
    K --> K3["LED"]
    K --> K4["摄像头"]
    K1 --> BLE["BLE 扫描与连接"]
    K2 --> BLE
    K3 --> BLE
    K4 --> DST["DeviceSkinTestActivity"]

    M --> AUTH{"头像：是否登录"}
    AUTH -- "否" --> LOGIN["LoginActivity"]
    AUTH -- "是" --> PROFILE["ProfileActivity"]
    M --> SH["SkinHistoryActivity<br/>测肤历史"]
    M --> DH["DeviceHistoryActivity<br/>设备历史"]
    M --> ML["Model3DListActivity<br/>3D 模型列表"]
```

## 2. 肤质检测、3D 模型与人脸检测主流程

```mermaid
flowchart TD
    A["首页测肤卡片"] --> B["SkinListActivity"]
    B --> C{"选择检测类型"}
    C -- "肤质检测 skin" --> S["SmartSkinTestActivity<br/>type=skin"]
    C -- "3D 人脸模型 3d" --> D["SmartSkinTestActivity<br/>type=3d"]
    C -- "人脸检测 face" --> F["SmartSkinTestActivity<br/>type=face"]

    S --> P
    D --> P
    F --> P

    P{"相机权限与隐私授权"} -- "通过" --> CAP["前摄实时人脸引导"]
    P -- "拒绝" --> STOP["提示并停止流程"]
    CAP --> WAY{"采集方式"}
    WAY -- "自动/手动拍照" --> PHOTO["拍照预览"]
    WAY -- "相册选择" --> PHOTO

    PHOTO --> NORMAL["图片标准化<br/>EXIF 旋转；前摄取消镜像"]
    NORMAL --> FACE{"最终照片静态人脸校验"}
    FACE -- "无人脸/识别失败" --> TIP["未检测到人脸弹窗"]
    TIP -- "重新拍照" --> CAP
    TIP -- "取消" --> PHOTO
    FACE -- "有人脸" --> OSS["上传 OSS"]

    OSS --> TYPE{"按 type 分流"}
    TYPE -- "skin" --> SR["SkinReportActivity"]
    TYPE -- "3d" --> TD["Scan3DActivity"]
    TYPE -- "face" --> FR["FaceResultActivity"]

    SR --> API1["POST /api/self-research-face/analysis"]
    API1 --> SRDATA["展示基础信息、雷达图、趋势、检测表格"]
    SRDATA --> EXTRA["补查报告时间<br/>轮询皱纹/痤疮结果"]
    SR --> HOME1["返回首页"]
    SR -. "无人脸后端兜底" .-> TIP

    TD --> API2["POST /api/3d/tasks"]
    API2 --> POLL["轮询任务状态"]
    POLL --> RESULT["短轮询模型结果地址"]
    RESULT --> MODEL["下载并渲染 GLB 模型"]
    TD -. "无人脸/生成失败" .-> TDTIP["提示框：重新拍照或重新生成"]
    TDTIP -- "重新拍照" --> D

    FR --> LANDMARK["MediaPipe 关键点检测"]
    LANDMARK --> OVERLAY["三庭五眼动态叠加"]
    LANDMARK -. "无人脸" .-> FRTIP["提示框：重新拍照或返回"]
    FRTIP -- "重新拍照" --> F
    OVERLAY --> HOME2["返回首页"]
```

### 测肤报告评分与时间规则

- 列表与报告统一优先展示 `skin_score`。
- `skin_score` 缺失时，报告才回退使用 `overall_score`。
- 新分析接口不返回 `created_at` 时，使用 `face_id + report_id` 补查报告详情时间。
- 皱纹、痤疮为独立异步结果；报告页继续获取并刷新对应卡片。

## 3. 测肤历史、报告对比与方案流程

```mermaid
flowchart TD
    A["我的 → 测肤历史"] --> B["SkinHistoryActivity<br/>人脸分组列表"]
    BLE["养肤设备连接成功"] --> B
    B --> C["选择人员"]
    C --> D["ReportListActivity<br/>报告列表"]

    B --> ADD["新增测肤"] --> CAP["SmartSkinTestActivity<br/>type=skin"]
    D --> R{"点击报告"}
    R -- "已完成" --> SR["SkinReportActivity<br/>type=list"]
    R -- "未完成" --> GEN["生成动画"] --> SOL["SolutionActivity"]

    D --> CMP["选择两条报告"] --> RC["ReportCompareActivity"]
    RC --> D

    SOL --> VIEW["查看方案与脸部图片"]
    SOL --> WORK["去护理 → WorkActivity"]
    SOL --> HOME["返回首页"]
    WORK --> STOP["开始/执行/安全停止设备方案"]
    STOP --> HOME
```

## 4. 3D 模型历史流程

```mermaid
flowchart TD
    A["我的 → 3D 模型列表"] --> B["Model3DListActivity<br/>人脸分组"]
    B --> C["选择人员"] --> D["Model3DReportListActivity"]
    B --> ADD["新增 3D"] --> CAP["SmartSkinTestActivity<br/>type=3d"]
    D --> ADD2["新增模型<br/>当前未传 type"] --> CAP2["SmartSkinTestActivity<br/>实际默认 type=skin"]
    D --> E{"选择任务"}
    E -- "已有任务" --> SCAN["Scan3DActivity<br/>3dType=list"]
    E -- "生成方案" --> SOL["SolutionActivity"]
    SCAN --> MODEL["加载历史 GLB 模型"]
```

## 5. 智能咨询流程

```mermaid
flowchart TD
    A["小远测肤 Tab"] --> B{"输入方式"}
    B -- "热门问题" --> SEND["发送问题"]
    B -- "键盘文本" --> SEND
    B -- "按住说话" --> REC["录制 WAV"]
    REC --> ASR["POST /api/asr/recognize"]
    ASR --> SEND

    SEND --> GUARD{"是否已有回复进行中"}
    GUARD -- "是" --> WAIT["提示等待，防重复发送"]
    GUARD -- "否" --> SSE["POST /api/chat/completions/stream"]
    SSE --> DELTA["收到首个 delta 立即显示"]
    DELTA --> TYPE["约 24ms 逐字输出<br/>积压时自动加速"]
    TYPE --> DONE["done：保存 session_id"]
    DONE --> NEXT["下一轮携带 session_id<br/>连续会话"]
    SSE -. "空闲超时/断流/服务错误" .-> ERR["保留部分回答并显示错误"]
```

## 6. 养肤设备与设备历史流程

```mermaid
flowchart TD
    A["首页设备卡片"] --> K["切换到小信养肤 Tab"]
    K --> T{"选择设备类型"}
    T -- "微晶 / 小超炮 / LED" --> PERM["蓝牙与定位权限"]
    PERM --> SCAN["BLE 扫描弹窗"]
    SCAN --> DEV["选择设备"]
    DEV --> CONN["GATT 连接与服务发现"]
    CONN -- "成功" --> SAVE["保存/获取服务端设备记录"]
    SAVE --> SH["SkinHistoryActivity"]
    CONN -- "失败" --> RETRY["提示并重新扫描"]

    T -- "摄像头" --> CAMERA["DeviceSkinTestActivity"]
    CAMERA --> WIFI["连接设备 Wi-Fi"]
    WIFI --> CTRL["相机连接"]
    CTRL --> ACT["拍照 / 水分读取 / LED 0-3 档 / 刷新"]
    ACT --> BACK["断开相机并返回"]

    M["我的 → 设备历史"] --> DH["DeviceHistoryActivity"]
    DH --> SEARCH["名称搜索/筛选"]
    DH --> HP["HistoryPlanActivity<br/>设备方案列表"]
    HP --> PD["PlanDetailActivity<br/>方案详情"]
```

## 7. 登录、注册与个人资料流程

```mermaid
flowchart TD
    A["我的 → 头像"] --> T{"Token 是否存在"}
    T -- "否" --> L["LoginActivity"]
    T -- "是" --> P["ProfileActivity"]

    L --> MODE{"选择方式"}
    MODE -- "短信登录" --> SMS["获取验证码 → 短信登录"]
    MODE -- "密码登录" --> PWD["手机号 + 密码登录"]
    MODE -- "注册" --> REG["验证码注册"]
    SMS --> AGREE{"隐私协议已勾选"}
    PWD --> AGREE
    REG --> AGREE
    AGREE -- "否" --> WARN["提示先同意"]
    AGREE -- "是" --> TOKEN["保存 access_token"]
    TOKEN --> MAIN["MainActivity 首页"]

    P --> EDIT["ProfileEditActivity<br/>编辑昵称/生日/地区/头像/密码"]
    P --> LOGOUT["退出登录确认"]
    LOGOUT --> CLEAR["清除 Token"] --> L

    API401["任意受保护接口返回 401"] --> CLEAR
```

### 认证请求保护

- 短信发送、短信登录、密码登录均携带唯一 `X-Aisia-Request-Id`。
- 相同认证接口与相同请求内容在进行中时全局去重。
- 登录提交有跨 Activity 实例的短暂冷却。
- 受保护接口返回 401 时，网络层统一清除 Token 并跳转登录页。

## 8. 页面路由表

| 模块 | 页面/组件 | 当前主要功能 | 主要去向 |
|---|---|---|---|
| 启动 | `SplashActivity` | 展示启动页约 2 秒 | `MainActivity` |
| 主框架 | `MainActivity` | 隐私授权、四 Tab Fragment 切换 | 首页 / 智能咨询 / 养肤 / 我的 |
| 首页 | `HomeFragment` | 轮播、测肤卡片、设备卡片、数据状态 | `SkinListActivity` / 养肤 Tab |
| 智能咨询 | `ScanFragment` | 热门问题、文本、语音、SSE 连续会话 | 当前 Fragment 内完成 |
| 养肤 | `SkincareFragment` | BLE 扫描连接、摄像头入口 | `SkinHistoryActivity` / `DeviceSkinTestActivity` |
| 我的 | `MineFragment` | 登录资料、测肤历史、设备历史、3D 历史 | 多个历史/资料页面 |
| 检测菜单 | `SkinListActivity` | 肤质、3D、人脸三类入口 | `SmartSkinTestActivity` |
| 智能采集 | `SmartSkinTestActivity` | 相机/相册、人脸校验、图片标准化、OSS 上传 | 报告 / 3D / 人脸结果 |
| 测肤报告 | `SkinReportActivity` | 雷达、趋势、检测结果、分数、时间、图片 | 首页 / 重新拍照 |
| 3D 结果 | `Scan3DActivity` | 建任务、轮询、下载、渲染 GLB | 返回 / 重拍 / 重试 |
| 人脸结果 | `FaceResultActivity` | 关键点、三庭五眼叠加 | 首页 / 重拍 |
| 测肤人员 | `SkinHistoryActivity` | 人脸分组、新增测肤 | `ReportListActivity` / 采集 |
| 报告列表 | `ReportListActivity` | 查看报告、双报告对比、生成方案 | 报告 / 对比 / 方案 |
| 报告对比 | `ReportCompareActivity` | 两份报告雷达与指标对比 | 返回报告列表 |
| 3D 人员 | `Model3DListActivity` | 3D 人脸分组、新增模型 | 3D 任务列表 / 采集 |
| 3D 任务 | `Model3DReportListActivity` | 历史模型、生成方案 | 3D 渲染 / 方案 |
| 方案 | `SolutionActivity` | 方案详情、图片、去护理 | `WorkActivity` / 首页 |
| 护理执行 | `WorkActivity` | 读取步骤、启动、执行、安全停止设备 | 首页 |
| 摄像头设备 | `DeviceSkinTestActivity` | Wi-Fi 相机、拍照、水分、LED 控制 | 返回养肤 |
| 设备历史 | `DeviceHistoryActivity` | 设备列表、本地搜索 | `HistoryPlanActivity` |
| 历史方案 | `HistoryPlanActivity` | 指定设备的方案列表 | `PlanDetailActivity` |
| 方案详情 | `PlanDetailActivity` | 单个设备方案详情 | 返回 |
| 登录注册 | `LoginActivity` | 验证码、短信登录、密码登录、注册 | 首页 |
| 个人中心 | `ProfileActivity` | 查看资料、退出登录 | 编辑资料 / 登录 |
| 编辑资料 | `ProfileEditActivity` | 保存资料、修改密码 | 个人中心 |
| 项目详情 | `ProjectDetailActivity` | 门店/日期/时段选择、预约 | `OnlineConsultActivity` |
| 在线咨询 | `OnlineConsultActivity` | 客服咨询界面 | 返回 |
| 推荐 | `RecommendActivity` | 查看推荐项目 | 项目详情 |

## 9. 当前隐藏、旧版或未完成入口

| 页面/功能 | 当前状态 |
|---|---|
| 首页轮播图详情 | 点击回调仍为 TODO，当前只支持轮播与指示点 |
| 拍照页“设置”按钮 | 显示“设置功能开发中” |
| 我的 → 护理 | XML 中隐藏，点击逻辑已注释 |
| `SkinTestActivity` | 旧版三角度测肤流程，Manifest 已注册，但当前首页主链不进入 |
| `SkinAnalysisActivity` | 旧版检测菜单，转到 `AiConsultActivity`；当前首页使用 `SkinListActivity` |
| `AiAnalysisActivity` | 旧版分析展示页，当前主采集流程直接进入报告 |
| `AiConsultActivity` | 旧版独立咨询页；当前底部第二 Tab 使用 SSE `ScanFragment` |
| `DeviceConnectionActivity` | 独立 BLE 扫描页已注册，当前养肤主链在 `SkincareFragment` 内完成扫描连接 |
| `Model3DReportListActivity` 的“新增模型” | 当前未传 `type=3d`，实际会进入默认肤质采集流程 |
| `RecommendActivity` / 项目预约链 | 页面存在，但当前主导航没有直接入口 |
| 方案脸部图片全屏预览 | 当前使用外部查看，代码中仍有 PhotoView TODO |

## 10. 关键参数传递

| 来源 → 目标 | 关键参数 |
|---|---|
| `SkinListActivity → SmartSkinTestActivity` | `type=skin/3d/face` |
| `SmartSkinTestActivity → SkinReportActivity` | `oss_key`, `image_path` |
| `SmartSkinTestActivity → Scan3DActivity` | `oss_key`, `image_path`, `3dType=img` |
| `SmartSkinTestActivity → FaceResultActivity` | `oss_key`, `image_path`, `deviceId` |
| `SkinHistoryActivity → ReportListActivity` | `faceId`, `deviceId`, `device_id` |
| `ReportListActivity → SkinReportActivity` | `type=list`, `faceId/id`, `reportId`, `deviceId` |
| `ReportListActivity → ReportCompareActivity` | `reportIdA`, `reportIdB`, `faceId` |
| `Model3DReportListActivity → Scan3DActivity` | `task_id`, `3dType=list` |
| 报告/3D 列表 → `SolutionActivity` | `report_id`, `deviceId`, `device_id` |
| `SolutionActivity → WorkActivity` | `report_id`, `deviceId`, `device_id` |

## 11. 关键接口概览

| 业务 | 接口 |
|---|---|
| 流式智能咨询 | `POST /api/chat/completions/stream` |
| 语音识别 | `POST /api/asr/recognize` |
| 发送验证码 | `POST /api/auth/app/sms/send` |
| 短信登录/注册 | `POST /api/auth/app/sms/login` |
| 密码登录 | `POST /api/auth/app/login` |
| 用户资料 | `GET /api/user/profile` |
| 新建测肤分析 | `POST /api/self-research-face/analysis` |
| 报告详情 | `GET /api/self-research-face/faces/{face_id}/reports/{report_id}` |
| 皱纹/痤疮异步结果 | `GET .../{report_id}/wrinkle`，`GET .../{report_id}/acne` |
| 3D 任务 | `POST /api/3d/tasks` |
| 3D 状态/结果 | `GET .../{task_id}/status`，`GET .../{task_id}/result` |
| 我的设备 | `GET /api/my-device` |
| 护理方案 | `POST /api/my-device/{device_id}/treatment-plans` |


# AISIA 系统架构流程文档

## 一、项目概述

AISIA 是一款 Android 美容护肤应用，提供智能测肤、蓝牙设备连接、皮肤报告分析等功能。

**技术栈：**
- 语言：Kotlin
- 架构：单 Activity + 多 Fragment
- 网络：OkHttp
- 图片加载：Coil
- 相机：CameraX
- 蓝牙：Android BLE API

---

## 二、系统架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AISIA Android App                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        Application Layer                         │   │
│  │  ┌─────────────────┐                                            │   │
│  │  │    AisiaApp     │  全局 Context、应用初始化                    │   │
│  │  └─────────────────┘                                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                         UI Layer (Activity)                       │   │
│  │                                                                   │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │   │
│  │  │  MainActivity   │  │ LoginActivity   │  │SmartSkinTest... │  │   │
│  │  │   (主框架页)     │  │   (登录页)       │  │   (智能测肤)     │  │   │
│  │  └────────┬────────┘  └─────────────────┘  └─────────────────┘  │   │
│  │           │                                                       │   │
│  │  ┌────────┴────────────────────────────────────────────────┐    │   │
│  │  │                    Fragment Container                    │    │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐           │    │   │
│  │  │  │HomeFragment│  │ScanFragment│  │Skincare...│           │    │   │
│  │  │  │   (首页)   │  │ (测肤Tab) │  │ (护肤Tab) │           │    │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘           │    │   │
│  │  └─────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        Network Layer                              │   │
│  │                                                                   │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │   │
│  │  │   HttpHelper    │  │  TokenManager   │  │   ApiConfig     │  │   │
│  │  │ (网络请求工具)   │  │  (Token管理)    │  │  (API配置)      │  │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Backend Server                                 │
│                    (API Base URL: 配置于 ApiConfig)                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块说明

### 3.1 Application 层

| 类名 | 职责 |
|------|------|
| `AisiaApp` | 全局 Application，提供全局 Context 访问点 |

### 3.2 UI 层 - Activity

| Activity | 职责 | 入口 |
|----------|------|------|
| `MainActivity` | 主框架页，承载底部导航和 Fragment | 应用启动 |
| `LoginActivity` | 手机号+验证码登录 | 未登录时/Token失效时 |
| `SmartSkinTestActivity` | 智能测肤（拍照→上传→分析→报告） | 首页/测肤Tab |
| `SkinAnalysisActivity` | 皮肤分析结果展示 | 测肤完成后 |
| `DeviceConnectionActivity` | 蓝牙设备连接 | 首页设备卡片 |
| `SkinReportActivity` | 皮肤检测报告 | 分析完成后 |

### 3.3 UI 层 - Fragment

| Fragment | 职责 | 所属Tab |
|----------|------|---------|
| `HomeFragment` | 首页轮播图、功能入口卡片 | 首页 |
| `ScanFragment` | 小远测肤功能列表 | 测肤Tab |
| `SkincareFragment` | 护肤设备连接（小钢炮/微晶/LED） | 护肤Tab |

### 3.4 网络层

| 类名 | 职责 |
|------|------|
| `HttpHelper` | 封装 OkHttp，支持 GET/POST/PUT，自动注入 Token，统一处理 401 |
| `TokenManager` | Token 持久化存储（SharedPreferences） |
| `ApiConfig` | API 基础配置（Base URL 等） |

---

## 四、核心业务流程

### 4.1 用户登录流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  输入手机号  │────▶│  获取验证码  │────▶│  输入验证码  │────▶│   登录请求   │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                    │
                                                                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   进入首页   │◀────│  保存Token   │◀────│  登录成功    │◀────│  解析Token   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**API 接口：**
- 发送验证码：`POST /api/auth/app/sms/send`
- 登录：`POST /api/auth/app/sms/login`

### 4.2 智能测肤流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  打开相机    │────▶│   拍照/选图  │────▶│   预览确认   │────▶│   上传图片   │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                    │
                                                                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  查看报告    │◀────│  完成动画    │◀────│  智能深度分析  │◀────│   上传完成   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**分析项目：**
1. 面部图像清晰度校准
2. 面部区域分割
3. 肌肤水分含量检测
4. 皮肤油脂分泌分析
5. 干纹、静态皱纹识别
6. 毛孔粗大程度测算
7. 黑色素、色斑检测
8. 泛红敏感区域识别

**API 接口：**
- 上传图片：`POST /api/skin/upload`

### 4.3 蓝牙设备连接流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  选择设备类型 │────▶│  权限检查    │────▶│  蓝牙扫描    │────▶│  显示设备列表 │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                    │
                                                                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  设备控制    │◀────│  连接成功    │◀────│  建立连接    │◀────│  选择设备    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**支持设备类型：**
- 小钢炮（深层清洁）
- 微晶（导入导出）
- LED（光疗护肤）

---

## 五、页面导航结构

```
MainActivity (主框架)
├── HomeFragment (首页)
│   ├── 轮播图 (Banner)
│   ├── 皮肤检测卡片 → SmartSkinTestActivity
│   └── 设备连接卡片 → DeviceConnectionActivity
│
├── ScanFragment (测肤Tab)
│   ├── 肌肤智能检测 → SmartSkinTestActivity (type=skin)
│   ├── 3D面诊 → SmartSkinTestActivity (type=3d)
│   └── 美颜检测 → SmartSkinTestActivity (type=face)
│
└── SkincareFragment (护肤Tab)
    ├── 小钢炮 → 蓝牙扫描 → 设备连接
    ├── 微晶 → 蓝牙扫描 → 设备连接
    └── LED → 蓝牙扫描 → 设备连接

LoginActivity (登录页)
└── 登录成功 → MainActivity

SmartSkinTestActivity (智能测肤)
├── 拍照/选图
├── 上传分析
└── 完成 → SkinReportActivity
```

---

## 六、网络请求机制

### 6.1 请求拦截器

```kotlin
// HttpHelper 认证拦截器
authInterceptor = Interceptor { chain ->
    val original = chain.request()
    val path = original.url.encodedPath
    val builder = original.newBuilder()
    
    // 非白名单接口自动注入 Authorization Header
    if (!isInWhiteList(path)) {
        val token = TokenManager.getToken()
        if (!token.isNullOrEmpty()) {
            builder.header("Authorization", "Bearer $token")
        }
    }
    chain.proceed(builder.build())
}
```

### 6.2 白名单接口

以下接口不需要 Token：
- `/api/auth/app/sms/send` - 发送验证码
- `/api/auth/app/sms/login` - 登录

### 6.3 401 统一处理

当任意接口返回 401 时：
1. 清除本地 Token
2. 跳转到登录页
3. 2秒内去重，避免并发请求重复跳转

---

## 七、数据存储

| 数据类型 | 存储方式 | 说明 |
|----------|----------|------|
| Token | SharedPreferences | `aisia_auth` 文件，key: `access_token` |
| 拍摄图片 | 外部存储 | `getExternalFilesDir(DIRECTORY_PICTURES)` |

---

## 八、第三方依赖

| 依赖 | 用途 |
|------|------|
| OkHttp | 网络请求 |
| Coil | 图片加载 |
| CameraX | 相机功能 |
| Material Components | UI 组件 |

---

## 九、资源结构

```
app/src/main/
├── java/com/example/aisia/
│   ├── AisiaApp.kt                    # Application
│   ├── MainActivity.kt                # 主框架
│   ├── network/
│   │   ├── HttpHelper.kt              # 网络请求
│   │   ├── TokenManager.kt            # Token管理
│   │   └── ApiConfig.kt               # API配置
│   └── ui/
│       ├── home/HomeFragment.kt       # 首页
│       ├── scan/ScanFragment.kt       # 测肤Tab
│       ├── skincare/SkincareFragment.kt # 护肤Tab
│       ├── login/LoginActivity.kt     # 登录
│       ├── skintest/
│       │   ├── SmartSkinTestActivity.kt # 智能测肤
│       │   └── SkinAnalysisActivity.kt  # 皮肤分析
│       ├── device/DeviceConnectionActivity.kt # 设备连接
│       └── report/SkinReportActivity.kt # 皮肤报告
└── res/
    ├── layout/                        # 布局文件
    ├── drawable/                      # 图形资源
    └── values/                        # 颜色、字符串等
```

---

## 十、状态管理

### SmartSkinTestActivity 状态机

```
STATE_PREVIEW (预览) ──拍照──▶ STATE_CAPTURED (已拍照)
      ▲                              │
      │                              ▼
      └────重拍────            STATE_ANALYZING (分析中)
                                     │
                                     ▼
                              STATE_COMPLETE (完成)
                                     │
                                     ▼
                              跳转报告页
```

---

*文档生成时间：2026-07-07*
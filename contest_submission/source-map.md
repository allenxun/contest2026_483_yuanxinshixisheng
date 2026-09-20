# 源码分类清单

## A 级 参赛主线

这些目录构成 VelaVision 的可交付主线，应在专属仓保持完整、可构建、可追溯。

| 类别 | 路径 | 责任 |
| --- | --- | --- |
| 芯片与板级适配 | `port/`、`board/kickpi_k7/` | RK3576/KICKPI K7 启动、defconfig、板级初始化、UART/USB 等边界 |
| 视频与视觉 | `app/k7host/`、`app/k7graph/`、`app/k7npu/` | 摄像头、视频流、人脸框、姿态和 NPU 诊断 |
| 云台与外设 | `app/gimbal/`、`mcu/` | 云台运动协议与外部控制器配套 |
| 无线与网络 | `app/k7radio/`、`app/k7usb/` | BLE 配网、Wi-Fi 状态、USB 链路 |
| 语音与业务闭环 | `app/k7agent/`、`app/k7audio/`、`app/k7sound/` | 语音意图、固定提示音、照片上传、任务状态和报告播报 |

## B 级 配套实现与验收

| 类别 | 路径 | 说明 |
| --- | --- | --- |
| 内存与存储 | `app/k7mem/`、`app/k7emmc/`、`app/k7storage/`、`app/k7fat/` | DDR、eMMC、存储和文件系统边界；仅提交与本项目相关的实现和说明 |
| 音频硬件 | `app/k7audiohw/`、`app/k7eh/`、`app/k7ehcontrol/` | 音频硬件、音频增强和控制器配套 |
| 主机网关 | `host/` | 上传、taskId/reportId 查询、brief 报告、TTS 和验收脚本 |
| 联调前端 | `frontend/` | BLE 配网、视频联调和状态呈现 |
| 测试与工具 | `tests/`、`tools/`、`config/`、`patches/` | O0/O2 回归、构建、校验、RAM 加载和日志工具 |

## C 级 文档、证据和 AI 材料

| 类别 | 路径 | 说明 |
| --- | --- | --- |
| 适配说明 | `docs/` | 需求、实现、测试、失败和交接记录；不删除失败记录 |
| 脱敏证据 | `evidence/` | 哈希、构建、串口摘要、状态和验收结果；原图与凭据留在 `private/` |
| 自建 Skill | `skills/k7-openvela-driver-port/` | 参赛要求的有效 Skill，描述驱动移植和证据流程 |
| AI 日志 | `logs/maomaojiang01/` | 通过 manifest 管理导出的真实 AI Coding 对话和校验结果 |
| 参赛材料 | `deliveries/` | 作品介绍文档、演示视频和最终提交包 |

## D 级 本地归档或未完成候选

以下目录不作为当前产品入口，除非某个文件被明确复核并移动到 A/B/C 级路径：

```text
legacy/          旧 PC 交付
baselines/       历史基线
vm-archive/      虚拟机归档
work-in-progress/未完成候选
private/         凭据、原图和私密运行材料
deploy/          临时部署输出
third_party/     外部依赖或来源材料
```

D 级目录可以保留来支撑历史追溯，但不应进入公开提交包，不能用其中的旧状态覆盖当前 `project-manifest.json` 和最新证据。

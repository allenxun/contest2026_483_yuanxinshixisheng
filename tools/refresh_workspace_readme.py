"""Preserve accumulated historical status, replace README with a clear entry."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
archive=R/'docs/README历史快照_20260910_块设备前.md'
if archive.exists():raise RuntimeError('Snapshot already exists; do not overwrite history')
archive.write_bytes((R/'README.md').read_bytes())
text='''# VelaVision

统一开发入口：`E:\\openvela\\VelaVision`。原生 openvela/NuttX、RK3576 BSP、视觉、无线、语音候选、前端与 AI 日志均在本仓库组织。

## 当前状态

- **eMMC：**原生低速初始化、单块重复读取、主备 GPT 和分区项 CRC 已真机通过；容量 61079552×512 字节，15 个现有分区。最新只读块设备候选 `emmc-block-20260910` 已编译，正在 RAM 加载，尚未验收。没有格式化或写盘。见 [eMMC 接入](docs/eMMC原生只读接入_20260910.md)。
- **无线：**原生 BLE 真配网、WPA2/DHCP 与 IP 事件已接通。最后 GPT 版本恢复后网关 5/5、30秒保持通过，测试客户端主动断开；当前 RAM 加载期间无线暂停。历史 reason 8 断连与长稳边界保留，不声称生产级稳定。见 `evidence/emmc-gpt-20260910/`。
- **DDR/CPU：**独立 1GiB CPU 模型池已在 model-arena 版本完成 384MiB 两轮稀疏读写及释放验证；后续镜像未重复该测试。系统堆仍约126MiB，CPU仍单核，未启用全部4GiB/八核。
- **视觉与 NPU：**保留已确认的人脸跟随、三视角拍照和固定 INT8 矩阵基线；完整 NPU 模型、仪器检测与整机联合验收未完成。当前任务不启动云台。
- **语音：**主机候选、共享 Wi-Fi broker 候选和 Windows 真实 ASR/TTS 模型运行已交接并核对哈希；未移植实际推理库或音频驱动到板端。次会话继续语音流收尾与内存测量。见 [交接记录](docs/VoiceLink交接接收与集成顺序_20260910.md)。
- **Agent：**尚未部署，模型方案和正式设备工具接口待定。

最后已验证镜像、正在构建/加载的镜像分别记录在 `project-manifest.json` 的 `current_device`、`pending_firmware`；实测只对相应版本有效。历史叙述完整保存在 [README 历史快照](docs/README历史快照_20260910_块设备前.md)。

## 开发位置

| 内容 | 位置 |
| --- | --- |
| 视觉、云台、NPU | `app/k7host/`、`app/gimbal/`、`app/k7npu/` |
| 无线、DDR、eMMC | `app/k7radio/`、`app/k7mem/`、`app/k7emmc/` |
| BSP 与构建配置 | `port/`、`board/kickpi_k7/` |
| 前端、主机、STM32 | `frontend/`、`host/`、`mcu/` |
| 未集成语音候选 | `work-in-progress/parallel-voicelink*`、`parallel-wifi-service` |
| 旧 PC 交付与证据 | `legacy/`、`baselines/`、`evidence/` |
| AI 日志 | **`logs/maomaojiang01/`** |

Ubuntu `/home/swl/openvela` 是外部 SDK，项目副本 `/home/swl/openvela/work/velavision-project`。先用 `tools/sync_sdk.py --check` 核对再同步；未知改动必须处理，不静默覆盖。独立版本构建记录在 `evidence/build/<revision>/verification.json`。已完成产物不覆盖；初始 `tools/build.sh` 不能代替最新版本构建记录。全新环境完整复现尚未验收。

## 日志与交付

队伍 `contest2026_483_yuanxinshixisheng`，GitHub 用户名 **maomaojiang01**。日志范围包含明确选定的旧主会话、当前主会话、VoiceLink 并行主会话及已采集的日志配置会话。`logs/maomaojiang01/manifest.json` 是数量、文件与哈希入口；按真实北京时间分日、跨日序号连续，保留脱敏、原生导出不完整及失败记录。

运行 `python tools/export_project_logs.py` 刷新显式会话，使用原版 `python tools/official-validator/tools/validate-log.py logs/` 校验。格式通过不代表比赛验收、完整无遗漏或已经上传。详见 [代码日志对应](docs/代码日志对应表.md) 与 [自动采集](docs/自动日志采集.md)。

Git 分支 `dev-ai-contest-2026`，来源为用户指定的 allenxun fork；当前本地整理未提交、未推送。最终正式源码、构建证据与日志统一交付，不把暂存候选或 Windows 运行结果冒充板端功能。
'''
(R/'README.md').write_text(text,encoding='utf-8',newline='\n')
print('README consolidated; previous content preserved in docs')

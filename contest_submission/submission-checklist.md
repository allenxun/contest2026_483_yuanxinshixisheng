# 比赛提交检查表

| 官方要求 | 当前入口 | 状态 |
| --- | --- | --- |
| 专属 GitHub 仓与 `dev-ai-contest-2026` 工作流 | `contest2026_483_yuanxinshixisheng.xml`、Git 分支 `dev-ai-contest-2026` | 提交前人工确认远程仓地址和 PR 状态 |
| openvela 硬件适配 | `port/`、`board/kickpi_k7/`、defconfig 和 `contest_submission/source-map.md` | 源码已归类；上游 PR 尚未提交 |
| UART 控制台与目标板启动 | `board/kickpi_k7/`、`evidence/`、`docs/` | 保留 NSH/串口证据，按当前镜像重新核对 |
| 必要驱动与构建配置 | `port/`、`board/kickpi_k7/`、`config/` | 提交前运行 SDK 差异检查和完整构建 |
| AI Coding 日志 | `logs/maomaojiang01/`、`tools/export_project_logs.py` | 刷新 manifest 并运行官方 validator |
| 自建 Skill | `skills/k7-openvela-driver-port/SKILL.md` | 已有一个有效 Skill |
| 作品介绍文档 | `deliveries/contest-report-20260919/` | 已生成，提交前人工检查姓名、队伍和统计值 |
| 演示视频不超过 5 分钟 | `E:\openvela\VIDEO\` 或 `deliveries/` | 已生成 3 分 58 秒剪辑版 |
| 代码、视频、文档和证据不泄露凭据 | `private/`、`.gitignore`、公开目录审计 | 提交前运行敏感信息扫描 |

## 不得写成已通过的项目

- 两小时预览、BLE、Wi-Fi 共存长测尚未通过。
- 十轮真实语音三视图上传和报告播报闭环尚未形成完整连续证据。
- 独立 Wi-Fi、BLE、后端异常恢复和中位数/最大延迟统计仍需实测。
- report-narration-stream 的 mock 文案不能作为正式 AI 报告。

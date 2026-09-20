# AI Coding 日志

本仓库日志归属：**maomaojiang01**。真实数据在 `maomaojiang01/`，已经移除模板 `your-github-login` 示例目录。

- `maomaojiang01/manifest.json`：唯一实时权威清单；目前包含三个显式项目主会话和三个日志配置/验收会话。
- `maomaojiang01/2026-09-03/`：旧开发主会话，含原生 BSP、视觉、跟随、拍照、NPU 阶段。
- `maomaojiang01/2026-09-08/` 及后续日期目录：当前主会话，含无线适配、BLE/前端、语音与统一集成；同一 session 跨日保持连续 seq。
- `tools/log-sources.json`：手动刷新范围，列出旧主会话、当前主会话和 VoiceLink 并行主会话。fork/subagent 不重复导出。

每个会话独立保留真实 ID、日期、连续 seq、原始时间、源行号和哈希。未补造历史代码提交、模型内部推理、用量或工时；未重复导出子任务继承的历史。具体范围、脱敏和截止时间见上级 `evidence/log-snapshots.json`。

用户级 Stop hook 已完成真实触发验收。当前长轮次另由 `tools/watch_project_logs.py` 每 30 秒监测当前主会话；切换模型但继续同一任务可沿用 session ID，新建任务则必须有意识地登记新 session。自动采集的范围、状态文件、失败边界和停用方法见 `docs/自动日志采集.md`。

在仓库根目录刷新显式项目主会话并按原版官方脚本校验：

```bash
python -X utf8 tools/export_project_logs.py
python -X utf8 tools/official-validator/tools/validate-log.py logs/
```

`health=degraded` 是对原生桌面导出范围、源端截断和未完成工具调用的诚实声明，不表示 JSONL 格式校验失败。格式 `ALL OK` 也不等于比赛验收、日志完整无遗漏或已上传。数量、文件数、哈希和最新校验时间始终以 `manifest.json` 与 `private/log-collector/official-validation.txt` 为准；`evidence/` 内的结果只是可提交快照。

导出会排除内部推理、system/developer 提示、ambient context 和媒体，脱敏已知密码、Token/Bearer、私钥、开发内网 IP 和 MAC；未知形式秘密仍需提交前人工检查。`private/` 不提交。源码和日志应在同一仓库一起提交；当前仍为本地整理，未 push。

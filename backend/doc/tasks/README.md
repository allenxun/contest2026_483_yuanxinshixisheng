# MVP 实施调度

执行顺序：A 基础完成并通过 Oracle 审查及 E 验收 → 总协调合入 dev → B/C/D 从该基线并行 → E 持续联调验收 → 总协调集成。master 暂不接入未验收代码。

| 包 | 工作树/分支 | 启动条件 | 任务书 |
|---|---|---|---|
| A | .worktrees/mvp-a / feature/mvp-foundation | 立即启动 | [A](A-foundation.md) |
| B | .worktrees/mvp-b / feature/mvp-identity-devices | A 验收合入 dev 后创建 | [B](B-identity-devices.md) |
| C | .worktrees/mvp-c / feature/mvp-care | A 验收合入 dev 后创建 | [C](C-care.md) |
| D | .worktrees/mvp-d / feature/mvp-assessments | A 验收合入 dev 后创建 | [D](D-assessments.md) |
| E | .worktrees/mvp-e / feature/mvp-acceptance | 立即启动，先准备验收 | [E](E-acceptance.md) |

先读 [公共规则](COMMON.md)。主协调在当前任务中进行，集成工作树为 .worktrees/integration。任务书不改变已有业务范围，真实供应商/设备证明/合规未落实时如实报告，不能伪造已经可上线。

## 任务面板

[查看五个工作包的当前进度](panels/README.md)。每个包独立面板，显示阶段、最新进展时间、提交、测试、阻塞与下一步。总协调每次巡检和收到里程碑报告后运行 `python3 backend/doc/tasks/update-panels.py` 刷新；不读取完整 OpenCode 输出。

每个面板现包含按模块分组的逐项任务清单和 Oracle 审查状态。M1/M2/M5 在 B，M3 在 D，M4 执行在 C、方案生成 Worker 在 D；A/E 为跨模块基础与验收。详见 COMMON.md 的 Oracle 门禁。

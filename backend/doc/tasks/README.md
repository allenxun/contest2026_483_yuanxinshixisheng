# MVP 实施调度

执行顺序：A 基础完成并通过 E 验收 → 总协调合入 dev → B/C/D 从该基线并行 → E 持续联调验收 → 总协调集成。master 暂不接入未验收代码。

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

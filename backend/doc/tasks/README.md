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

## 模块编号与实施包映射

模块 M1～M5 沿用原 API 设计，不因实施分工重编号。工作包字母 A～E 与模块编号是两个概念。

| 业务模块 | 实施包 | API 范围 |
|---|---|---|
| M1 身份与查看授权 | B | M1-A01～03 |
| M2 设备管理 | B | M2-A01～08 |
| M3 测肤任务与报告 | D | M3-A01～06 |
| M4 护理管理 | C：Java 查询/执行/记账；D：Python 方案生成 | M4-A01～09 由 C 实现 |
| M5 通知 | B | M5-A01 |

A 提供公共基础，E 验收全部模块。测试矩阵的负责人列按此映射；不修改现有场景编号、API 编号或业务含义。

## A 候选交接确认（2026-09-10）

候选代码 `26d97fbe908cb93c1fe366e28ba54a91c21b497c`，报告提交 `617354d0634c55b9420a3256c619186a1177b3c3`；Oracle PASS-with-notes，仅批准交 E 独立验收，未开放 B/C/D。

总协调确认：五个内部诊断 JSONB 列的版本豁免见数据架构；业务非空载荷仍按服务端/schema 校验 JSON 整数版本，DB 的 number 校验仅为第二层保障。E 应核对当前 Java/Python 写入边界拒绝非法版本，后续 B/C/D 不得直接绕过。默认媒体 deny-all 仅为安全基础，业务媒体权限须在后续包实现；真实提供方仍未接入，测试替身并发限制不代表生产可用。

## RV-5：基础 echo 查询边界（2026-09-11）

`GET /api/v1/system/echo-jobs/{id}` 仅允许已认证创建主体查询自己创建的 `system.echo` 任务；创建主体必须来自后端持久化的可信信息，不能由 GET 输入指定。非创建者、非 echo 类型和不存在统一返回 404 不可见，认证失败仍 401。POST 去重重放及响应投影也不得绕过该边界。不把诊断入口当作业务异步任务查询 API，不新增业务表。此为 E RV-5 的最小范围裁定，由 A 实现并 Oracle 复审，E 定向复验后才能放行 B/C/D；已闭合的诊断泄漏与 9 处消费点证据保留。

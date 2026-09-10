# 实施公共规则

用户已授权：A 先交付基础，随后 B/C/D 并行，E 全程跟进；具体编码由本机 OpenCode 的 orchestrator 完成。Codex 任务负责监督、必要审批、验证和结构化汇报。

## Token 与沟通

- 一次下发任务书，之后不要进行 Codex 与 Orchestrator 的开放式反复对话。
- 正常运行只读服务状态、权限/问题事件、Git 摘要和测试退出码，不把思考过程、工具全文或完整会话导出送入第二个模型。
- 故障时先读最后一个错误的最小片段（建议最多 2000 字符），再决定是否需要修复指令。任务确有缺口时允许一次具体纠偏，不机械重复提示继续。
- 完成报告不超过 500 字，必须包含 commit、测试命令/结果、剩余阻塞。伪造通过或只靠 mock 宣称真实服务已接入不可接受。

## 分支和文件归属

- master 为稳定基线，dev 为集成分支；各工作包 feature/mvp-* 独立 worktree。仅总协调任务集成 dev，未经请求不发布 master、不推送远端。
- 所有工作树位于本项目 .worktrees/，不访问旧 openvela 文档或其他业务仓库。只在分配的工作树写代码。
- A 独占公共构建、数据库迁移、契约 Schema、认证/幂等/OSS 基础适配、Python 队列运行时；后续共享变更提交请求，由总协调安排唯一负责人。
- B 独占 identity/devices/notifications 业务及 notifications Python handler；C 独占 care Java 业务；D 独占 assessments Java 业务及 assessment/identity-enroll/plan Python handler；E 独占 backend/acceptance 的黑盒测试及验收资料。
- 不修改 backend/doc/site 或 web；不在各包重写主设计。契约缺口记录到本包交付说明，协调后统一更新。
- 不删除/修改用户 logs，不触碰其他工作树。总协调可读取项目 .coordination 下各包的结构化状态用于调度；其他包不能以此获得修改别组代码的权限。

## 权限和运行隔离

- 当前 worktree 内普通读写、构建、测试可批准；只读编译器/SDK/依赖缓存目录可按实际需要批准。具体工具的自动安全审查仍必须遵守。
- 不使用 opencode --auto，不改变全局权限为 allow-all，不无条件批准 external_directory 通配访问。
- 项目外业务源码、私人文件、真实密钥、真实人脸上传、付费开通、生产修改、远端推送/发布、破坏性清理不在本轮一般实施授权内；权限事件逐项核实，不能当确认按钮全点。
- 测试数据库/容器/端口按 worktree 隔离，不能以共享同一个数据库来并行跑会清理数据的测试。
- 使用用户已配置的 OpenCode orchestrator 和默认模型；不擅自切换模型、提供方或 omo 配置。

## 监督和状态

- 在本项目 .coordination/<包名>/ 保存精简状态：worktree、branch、opencode session/server（不含密码）、phase、last_progress_at、commit、tests、blocker、next_action。
- OpenCode 凭据只保存在权限受限的运行时位置/环境，不进入状态、Git、日志或回复。
- 权限/问题/执行结束事件及时处理；30 分钟巡检作兜底，正常进行不重复发消息。先使用确定性工具过滤事件，只有需判断时才唤起模型。
- 服务/机器休眠会影响巡检，不声称无人值守监控永远在线。
- 成功先本包提交，汇报总协调并等待集成；不自行合并其他包、不反复新建 OpenCode 会话。

## 面板维护

各包监督任务维护自己的精简 status.json，可增加 completedItems（已验证完成项），测试和下一步应及时更新。总协调统一生成 backend/doc/tasks/panels/ 下总览与 A—E 面板；各 feature 不直接修改其他包或主工作树面板。半小时巡检和里程碑时刷新，只有证据支持才标记完成。

## Oracle 审查门禁（用户新增要求）

每个业务模块完成后，必须由 OpenCode 的 Oracle 审查。A 公共基础、E 验收框架也遵循此门禁。B 按 M1/M2/M5 分别给结论；C 对 M4 执行与记账给结论；D 对 M3 和 M4 方案生成 Worker 给结论，最终由 E 验证 M4 跨包链路。

流程：实施与自测 → 提交候选代码 → Orchestrator 实际调用已安装 Oracle → 修复阻塞 → Oracle 复审最终代码 → E 独立验收 → 总协调确认集成。为让 E 执行测试，可以集成候选到隔离 dev；在 Oracle 与 E 均通过前，不开放下一阶段、不声称已验收。

监督任务核实实际 Oracle 名称与调用结果，不擅自换模型，不用 Codex 自己审查冒充 Oracle。Oracle 不可用、调用失败或没有结论时记录 blocked；有阻塞问题时不通过。审查至少覆盖需求/任务清单、模块边界、API/数据库契约、权限、幂等与并发、恢复路径、测试证据和生产接入限制。只给 Oracle 相关设计及代码范围，监督任务只读精简报告，不搬运完整对话。

报告保存 backend/handoffs/<包>-oracle.md，包含模块、审查代码 SHA、结论、问题严重度/位置/复现方式、修复与复审结果、残留限制。报告可以单独提交；必须标明被审查代码提交，后续代码变化需复审，纯报告提交不必循环审查自身。

本包 status.json 增加 oracleReview：status（pending/running/changes_requested/passed/blocked）、reviewedCommit、report、blockingFindings。增加 taskProgress，以 checklists.json 的稳定编号为键，每项记录 status（pending/in_progress/blocked/done）和 evidence。只有 done 且有证据的项才在面板勾选。不要因整体 phase=complete 就自动勾选所有任务。

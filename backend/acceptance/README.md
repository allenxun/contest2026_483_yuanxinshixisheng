# E 黑盒验收（backend/acceptance）

E 工作包的机器可执行验收框架：**纯黑盒、HTTP 驱动**，只通过 27 个对外 API 观察系统
行为；不含、也不允许包含任何业务实现或生产替身代码。矩阵唯一数据源为
`backend/doc/测试场景清单-V1-五模块与双控制.md`（94 场景）与
`backend/doc/后端API接口设计-V1-五模块与流程对应.md`（27 API），由
`matrix/generate_matrix.py` 机械提取生成，`tests/test_matrix_integrity.py` 用独立
解析器逐项复核。

## 诚实声明（当前状态）

A 基线（公共构建、14 表迁移、认证主体上下文、幂等/代次公共设施、外部适配端口）**尚未
交付**：`config/baseline.json` 为 `{"gate":"closed","a_baseline":{"sha":null}}`，
**全部 94 个场景节点状态为 `dependency_pending`**。框架把这类挂起与普通 skip 分开统
计，matrix 模式最终退出码为 **3（绝不返回 0）**——不允许以全 skip 冒充通过。

## 目录

| 路径 | 说明 |
| --- | --- |
| `run.sh` | 一键入口：`setup-venv` / `selfcheck` / `matrix` |
| `requirements.txt` | pytest==9.1.1、requests==2.34.2（.venv 实际安装版本） |
| `config/baseline.json` | A 基线门控（A 交付后由协调者填 sha/synced_at 并置 `"gate":"open"`） |
| `config/acceptance.env.example` | E 专用隔离环境变量样例（占位符，无真实凭据） |
| `matrix/scenarios.json` | 94 条场景追踪矩阵（字段含 status/blocked_by/pending_reason 等） |
| `matrix/apis.json` | 27 个 API 反向索引（与 scenarios 双向一致） |
| `matrix/generate_matrix.py` | 文档 → JSON 再生成脚本 |
| `framework/conftest.py` | pytest 插件：markers 注册、dependency_pending 统计、退出码 3 |
| `framework/gate.py` | 基线门控与 94 个场景测试节点工厂 |
| `framework/client.py` | 黑盒 HTTP 客户端（requestId/超时/reports/ 证据落盘） |
| `framework/isolation.py` | run-id 前缀、E 专用 DB/端口约定、fail-closed 校验、清理计划 |
| `framework/doubles.py` | 替身声明与 `doubles_pass`/`real_pass` 证据分级（仅结构与标签） |
| `plans/A-baseline-plan.md` | A 基础验收计划（逐条可执行检查） |
| `plans/isolation-and-doubles.md` | 隔离数据与外部替身设计 |
| `tests/test_matrix_integrity.py` | 矩阵完整性自检（真实执行） |
| `tests/test_framework_selfcheck.py` | 框架自检（真实执行） |
| `tests/scenarios/` | 10 个小节模块，94 个节点一一对应场景 ID |

## 运行

```bash
cd backend/acceptance
./run.sh setup-venv   # 首次：建 .venv 并装依赖（或在仓库根: backend/acceptance/run.sh setup-venv）
./run.sh selfcheck    # 只跑框架/矩阵自检 → 期望退出码 0
./run.sh matrix       # 全量 24 自检 + 94 场景 → 当前期望退出码 3
```

退出码语义：`0` 全部真实通过；`1` 存在失败；`3` matrix 模式下存在 dependency_pending
（或有失败时仍为 1）。终端摘要固定输出
`PASSED=n DEPENDENCY_PENDING=m FAILED=k SKIPPED_OTHER=s MODE=...`。

## 状态语义

- **passed**：场景步骤真实执行并通过，`reports/evidence/<run-id>/` 有请求/响应证据，
  且证据标签（doubles.py）与结论匹配。
- **failed**：执行了但行为不符合清单检查要点 → 记录 requestId、响应与差异，报总协调。
- **dependency_pending**：因 A 基线未交付而无法执行。skip reason 固定前缀
  `dependency_pending: `，原因逐条来自矩阵 `pending_reason`，不是通过。

## A 基线交付后的流程

1. 协调者把 A 已提交基线同步到本工作树，更新 `config/baseline.json`
   （`a_baseline.sha`/`synced_at`，`"gate":"open"`）。
2. 先跑 `./run.sh selfcheck` 确认框架完好，再按 `plans/A-baseline-plan.md`
   执行基础验收；A 未通过不启动 B/C/D 的验收。
3. gate=open 后，未编写步骤的场景节点会**失败**并提示
   `scenario steps not yet authored`（防止开闸后空跑冒充通过）；按矩阵逐场景补写
   黑盒步骤（client + isolation run-id + doubles 声明），P0 优先。
4. 证据与报告（含基线 SHA、命令、退出码、PASSED/PENDING/FAILED、阻塞包名）交总协调。

## 约束

只读本工作树 `backend/doc/`；不访问兄弟工作树；不改生产实现/迁移/Schema/A 的构建配置；
不上传真实人脸、不购买服务、不部署生产。测试数据一律走隔离约定
（`plans/isolation-and-doubles.md`）。

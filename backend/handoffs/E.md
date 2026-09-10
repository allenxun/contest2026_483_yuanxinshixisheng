# E 工作包交接（backend/acceptance）

分支 `feature/mvp-acceptance`。本包为纯黑盒验收框架（HTTP 驱动），无任何业务实现。
本文件由 E 于 2026-09-10 生成。本包实施产物已由本包本地提交（实施提交 `cea01f7`，
含 backend/acceptance 全部产物与本交接文档）；集成合入由总协调负责，本包不推送远端。

## 产物清单

- `backend/acceptance/README.md` —— 目的、状态语义、运行命令、诚实声明
- `backend/acceptance/run.sh` / `requirements.txt` / `.gitignore` / `pytest.ini` / `conftest.py`
- `config/baseline.json`（当前 `gate=closed, sha=null`）、`config/acceptance.env.example`
- `matrix/scenarios.json`（94）、`matrix/apis.json`（27）、`matrix/generate_matrix.py`（文档→JSON 再生成）
- `framework/`：`conftest.py`（插件：markers 注册、dependency_pending 统计、matrix 退出码 3）、
  `gate.py`、`client.py`、`isolation.py`、`doubles.py`
- `tests/test_matrix_integrity.py`、`tests/test_framework_selfcheck.py`、
  `tests/scenarios/test_sc00.py..test_sc07.py,test_scc.py,test_scr.py`（94 节点，名称含场景 ID）
- `plans/A-baseline-plan.md`（AB-01..AB-10）、`plans/isolation-and-doubles.md`

## 矩阵统计（逐行提取，与文档声明核对）

- 总数 **94**；**P0=69、P1=25，与清单声明一致**（自检断言核对文档原句）。
- 分节：SC-00×4、SC-01×18、SC-02×11、SC-03×9、SC-04×10、SC-05×7、SC-06×9、
  SC-07×7、SC-C×5、SC-R×14。
- 范围：后端 49（现在可自动）、集成 12（需替身）、联调 33（需真实设备或APP）。
- API：27 个全部有场景回链；SC-C-01 按"全部 27 个 API"展开，与文档覆盖汇总表
  交叉核对一致（该表未展开 SC-C-01，本矩阵已展开并在测试中注明）。
- 包归属：M1/M2/M5→B、M3→C、M4→D（组合场景多包），全部 blocked_by 含 `A-baseline`。

## 自检命令与退出码（2026-09-10 实际执行）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `python3 -m venv backend/acceptance/.venv && backend/acceptance/.venv/bin/pip install -r backend/acceptance/requirements.txt`（工作树根执行） | 0 | pytest 9.1.1 / requests 2.34.2 |
| `backend/acceptance/run.sh selfcheck` | **0** | 24 passed（矩阵完整性 + 框架自检） |
| `backend/acceptance/run.sh matrix` | **3** | `PASSED=24 DEPENDENCY_PENDING=94 FAILED=0`，collected 118 |

## dependency_pending 语义

gate=closed 时 94 个场景节点以 skip 抛出、reason 固定前缀 `dependency_pending: `，
插件将其与普通 skipped 分开统计；matrix 存在 pending 时最终退出码固定 3，**绝不 0**。
gate 打开后未编写步骤的节点会直接 fail（防"开闸空跑冒充通过"）。

## 待 A 基线后的执行流程

1. 协调者同步 A 已提交基线进本工作树 → 更新 `config/baseline.json`
   （`a_baseline.sha`/`synced_at`、`"gate":"open"`）。
2. `./run.sh selfcheck` 确认框架完好。
3. 按 `plans/A-baseline-plan.md` 执行 AB-01..AB-10 基础验收，产出含基线 SHA、命令、
   退出码、请求/响应证据（`reports/evidence/`）的报告交总协调；A 未通过则不启动 B/C/D。
4. gate=open 后按矩阵补写并运行场景步骤（P0 优先），证据严格区分
   `doubles_pass` / `real_pass`（见 `plans/isolation-and-doubles.md`）。

## 状态

- blocker：**A 基线未提供**（无已提交的可构建 Java/Python、迁移、认证、幂等、
  适配端口），94 场景全部 dependency_pending，原因逐条见 `matrix/scenarios.json`。
- nextAction：**waiting_dependency**（等待协调者提供 A 基线 SHA 并更新门控）。
- 未修改 `backend/doc/**`、生产实现、迁移、Schema、A 构建配置；未访问兄弟工作树。
- 提交状态：本包已本地提交（实施提交 `cea01f7`；本交接说明的事实性修正另以独立
  提交记录），由总协调负责集成，未推送远端。
- 监督已独立复核上表自检结果（selfcheck exit=0、matrix exit=3）；该结果为框架
  自检与依赖挂起状态，不构成业务验收通过。

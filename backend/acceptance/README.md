# E 黑盒验收（backend/acceptance）

E 工作包的机器可执行验收框架：**纯黑盒、HTTP 驱动**，只通过 27 个对外 API 观察系统
行为；不含、也不允许包含任何业务实现或生产替身代码。矩阵唯一数据源为
`backend/doc/测试场景清单-V1-五模块与双控制.md`（94 场景）与
`backend/doc/后端API接口设计-V1-五模块与流程对应.md`（27 API），由
`matrix/generate_matrix.py` 机械提取生成，`tests/test_matrix_integrity.py` 用独立
解析器逐项复核。

## 诚实声明（当前状态）

A 基线（公共构建、14 表迁移、认证主体上下文、幂等/代次公共设施、外部适配端口）已交付，
E 已完成独立基础验收：**结论为未通过**——52/52 唯一结算中 51 PASS / 1 FAIL（A 缺陷：
`system.echo` GET 原样投影 `data.lastError`，含敏感标记串且未限大小；最小复现见
`evidence/A-baseline-*/logs/n2-http-repro.txt`）；**待 A 修复后绑定新 A SHA 定向重验**。
当前业务阻塞为 **B/C/D 业务实现未集成**（26 个业务端点为 501 NOT_IMPLEMENTED stub）。
`config/baseline.json` 保持 `"gate":"closed"`，**全部 94 个场景节点状态为
`dependency_pending`**。框架把这类挂起与普通 skip 分开统计；matrix 模式另有一层结算守卫：
94 个场景必须逐一唯一结算，否则退出码 4——**任何情况下绝不返回 0**，不允许以全 skip、
空收集或改命令行选项冒充通过。

## 目录

| 路径 | 说明 |
| --- | --- |
| `run.sh` | **唯一验收入口**：`setup-venv` / `selfcheck` / `matrix`；拒绝外部 `PYTEST_ADDOPTS`、绑定 RUN_ID、pytest 退出后校验结算哨兵 |
| `requirements.txt` | pytest==9.1.1、requests==2.34.2（.venv 实际安装版本） |
| `config/baseline.json` | A 基线门控（A 交付后由协调者填 sha/synced_at 并置 `"gate":"open"`） |
| `config/acceptance.env.example` | E 专用隔离环境变量样例（占位符，无真实凭据） |
| `matrix/scenarios.json` | 94 条场景追踪矩阵（字段含 status/blocked_by/pending_reason 等） |
| `matrix/apis.json` | 27 个 API 反向索引（与 scenarios 双向一致） |
| `matrix/generate_matrix.py` | 文档 → JSON 再生成脚本 |
| `framework/conftest.py` | pytest 插件：markers 注册、dependency_pending 统计、94 场景结算守卫（退出码 4）、passed 绑定证据强制、结算哨兵 `reports/<RUN_ID>/settlement.json` |
| `framework/gate.py` | 基线门控与 94 个场景测试节点工厂 |
| `framework/client.py` | 黑盒 HTTP 客户端（requestId/超时/reports/ 证据落盘；Authorization 等默认无条件脱敏） |
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
./run.sh matrix       # 全量（框架自检 + 94 场景节点）→ 当前期望退出码 3
```

退出码语义：`0` 94 场景全部真实通过且证据齐备；`1` 存在失败；`3` matrix 模式下存在
dependency_pending；**`4` 结算不完整/入口被篡改/哨兵校验失败**——94 个 sc_id 未逐一
唯一结算（缺失/未收集/被 `--ignore`/`-m` deselect/重复异常）、存在普通 skipped
（SKIPPED_OTHER>0），或入口防线被触发。**防假 0 是双层结构**：
① `run.sh`（唯一验收入口）检测到外部 `PYTEST_ADDOPTS` 注入（如
`-p no:framework.conftest` 禁用结算插件）即拒绝执行并 exit 4；运行时显式清空该变量
并注入本次生成的 `E_ACCEPTANCE_RUN_ID`；
② 插件在 session 结束写结算哨兵 `reports/<RUN_ID>/settlement.json`（mode、run_id、
settled_unique、四类计数、settlement_ok、completed），`run.sh` 在 pytest 退出后校验
哨兵存在、RUN_ID/mode 匹配、matrix 结算 94/94 且计数与汇总行一致，缺失/不匹配一律
无视 pytest 退出码强制 4——插件被禁用时必然无哨兵，0 不可能从本入口产生。
插件层守卫本身也独立生效（直调 pytest 同样非 0），但**直接裸调 pytest 不是验收入口，
其结果不被承认为验收证据**。未注入模式时默认按 matrix 处理（fail-safe）。
终端摘要固定输出
`PASSED=n DEPENDENCY_PENDING=m FAILED=k SKIPPED_OTHER=s MODE=... RUN_ID=...` 与
`SETTLED=x/94 EVIDENCE_TAGS ...`。

## 状态语义

- **passed**：场景步骤真实执行并通过，且**passed 与证据强绑定**：插件强制要求该
  sc_id 节点经 `scenario_evidence` 夹具记录 ≥1 条 HTTP 证据（reports/evidence/）并
  显式 `seal()` 替身声明；缺失即被改判 fail（"pass without evidence"）。证据标签按
  `no_externals`/`doubles_pass`/`mixed`/`real_pass` 分类计数输出，禁止以替身结果申报
  real_pass。
- **failed**：执行了但行为不符合清单检查要点（含裸通过被判 fail）→ 记录 requestId、
  响应与差异，报总协调。
- **dependency_pending**：因 B/C/D 业务实现未集成而无法执行（A 基线已交付并验收）。skip reason 固定前缀
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

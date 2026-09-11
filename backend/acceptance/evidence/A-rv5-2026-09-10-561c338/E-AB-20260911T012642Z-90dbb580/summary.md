# E RV-5 有界复验（PARTIAL）——A 561c338137aa，run E-AB-20260911T012642Z-90dbb580

> **RV-5 有界复验（PARTIAL），非新 SHA 全量验收**：只复验 RV-5 裁定（echo 归属 + GET/POST 统一 404 + dedup 碰撞）；历史适用证据见 RV5-8 台账。

新 A 候选：code=561c338137aaa1da7c8e00969da3c5381207b194 report=5ae53b6 dev=9b3e4a1 integrated=e1d54b92e8b6b20a1e1b5631cc17be95b8d5e2a1

## 结算：10/10 唯一结算；10 PASS / 0 FAIL / 0 BLOCKED / 0 INFO（计数和=10==行数 10）；final_exit=0

**RV-5 有界复验（PARTIAL）结果：通过**——10 PASS / 0 FAIL / 0 BLOCKED。组合意见：本次有限验证 + 历史适用证据（A-baseline 26d97fb / A-reverify f6e500e），整体验收意见由总协调形成；本报告不输出全量通过或 A 基础验收结论。

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| RV5-1 | 从当前源码重建：A 源码==561c338（git diff 空）+ mvn 重建 jar + 启动健康；未用镜像 | **PASS** | git diff 561c338 -- web-java worker-python contracts; mvn -DskipTests package; java -jar / 0 | diff_empty=True HEAD=cce397560ef3 jar=web-java-0.0.1-SNAPSHOT.jar sha256[:16]=c12077b9a8f42924 health_up=True；同源各自重建，jar 哈希可能因构建元数据不同而非字节一致 |
| RV5-2 | GET 创建者可见 + 泄漏点抽查回归：jobId 关联 + 投影仅 closed enum，合成 marker/原始 code 缺席 | **PASS** | POST echo → 创建者 GET（jobId 断言）+ SQL marker → GET / 200/200 | creator=jobId 匹配; lastError=None / marker_seed_rows=1 / jobId 匹配; lastError={'reason': 'internal', 'retryable': True} |
| RV5-3 | GET 三态统一 404 不可区分：外来/不存在/非 echo——完整公开响应（仅排除 requestId）规范化等值 + 全态无归属/类型/payload 泄露 + 种子回查 | **PASS** | 三态 GET + 完整 body 规范化逐字节比较 + INSERT RETURNING 回查 / 404/404/404 | accounts_differ=True s1_valid=True s2_valid=True status=404/404/404 public_body_equal=True forbidden_hit=[] seed_ok=True(rows=1) back=51d0e105-2a2c-4beb-9ea3-5e830d4a7245/rv5.non-echo/8ba2d082-0fd9-43e2-a65d-1a56d4ca26dd codes_ok=True |
| RV5-4 | 未认证/伪造凭据 → 401（基本错误信封检查，非严格 schema） | **PASS** | GET echo job 无 token/伪造 token / 401/401 | no-token=401/AUTH_REQUIRED forged=401/SESSION_INVALID |
| RV5-5 | POST dedup 碰撞矩阵（①无键 404 ②keyed 404+T13 rejected ③重放同一拒绝+T13 复验 ④SELECT * 全字段行不变 ⑤无 B 属行 ⑥同主体正例）：统一完整拒绝体等值+防投影 | **PASS** | A 显式 body.jobId 建 job → B 同 jobId 无键/keyed 碰撞/重放 + SQL 查证 / 404/404/404/200 | worker_running_during_window=False（本项不启 worker，无并发修改） / no-key: 404/RESOURCE_NOT_VISIBLE / keyed#1: 404 t13=rejected/RESOURCE_NOT_VISIBLE / keyed#2: 404 t13_replay=rejected/RESOURCE_NOT_VISIBLE / deny_body_equal=True forbidden_hit=[] / A_row_full_snapshot_unchanged=True B_owned_rows=0 / positive_replay: 200 same_job=True |
| RV5-6 | 有界严格响应契约：成功投影走严格 schema（validate_responses）+ selftest 10/10 + samples 50 + OpenAPI；404/401 仅基本信封检查（如实分类） | **PASS** | validate_responses <200 捕获>; --selftest; validate_samples; openapi_spec_validator / 0/1 | selftest=True samples=True(50) oas=True captured_200_strict=True / 404/401=基本信封检查: 2Z-90dbb580/logs/responses/rv5-6-1.json ok /home/lousuan/lansee/openvela/conte |
| RV5-7 | 已接受限制披露：全局 dedup availability-oracle（碰撞 404 vs 新键 200 仅揭示 dedup 键不可用；完整 POST 存在性不可区分=单独决策，A 未决项 11） | **PASS** | 读 decisions-notes.md §11 + A.md 核对该披露 / 0 | decisions_dedup_boundary=True A_md_availability_oracle=True |
| RV5-8 | 历史证据台账+SHA 适用范围：既有基础/定向证据存在；f6e500e..561c338 未改 9 处消费点文件 → f6e500e 复核台账仍适用（组合意见=本次有限验证+历史证据） | **PASS** | 检查证据目录存在 + git diff --name-only f6e500e 561c338 / 0 | dirs={'A-baseline-2026-09-10': True, 'A-reverify-2026-09-10': True} changed_files=15 consumption_point_files=[] |
| CLEANUP | 停进程并按 run 标签删除 mvp-e-pg | **PASS** | docker rm -f -v / 0 |  |
| CLEANUP-ports | 端口释放 | **PASS** | ss / 0 |  |

## 严格 vs 基本校验分类
- 严格 schema：echo-job-view 200 成功投影（validate_responses 机制）。
- 基本错误信封检查（非严格 schema）：404/401/keyed 拒绝重放——OAS 严格机制当前只解析 echo-view 200 路径。

## 组合意见边界
本次为 RV-5 限定的有界验证；整体验收意见=本次有限验证 + 历史适用证据（A-baseline-2026-09-10=26d97fb；A-reverify-2026-09-10=f6e500e），由总协调形成；本报告不输出全量通过或 A 基础验收结论。

## A 缺陷清单

（无 FAIL 项）

## 附件
- `logs/rv5-*.log`、`logs/responses/`、`logs/rv5-5-*.log`

# E C/M4 黑盒验收 —— C 8b3592e，run E-AB-20260911T080517Z-76687307

> **替身形态（doubles_pass）**：短信/会话/设备凭据/存储/人脸均为 dev 替身；种子=直连 SQL，不等于跨包真实链路。D 真实端点（方案生成、真实任务替换）与 B 真实端点（授权/成员/设备）相关场景仍 dependency_pending。

## 结算：3/14 唯一结算；3 PASS / 0 FAIL / 0 BLOCKED / 0 INFO（计数和=3==行数 3）；final_exit=4

**C/M4 黑盒验收结果：未通过**——结算不完整。

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| CC-01 | 构建与启动绑定：HEAD=93b7e33、8b3592e 祖先、源码 diff 空、当前源码构建、health UP | **PASS** | git merge-base/diff; mvn -DskipTests package; java -jar / 0 | HEAD=93b7e33de486 ancestor=True diff_files=[] jar=web-java-0.0.1-SNAPSHOT.jar sha16=7c79f7cc3ea39a76 |
| CLEANUP | 停进程并按 run 标签删除 mvp-e-pg | **PASS** | docker rm -f -v / 0 |  |
| CLEANUP-ports | 端口释放 | **PASS** | ss / 0 |  |

## C 缺陷清单

（无 FAIL 项）

## 待集成/依赖披露

- D：M3-A01 真实方案生成与任务替换链路、plan_payload 版本化白名单批准 → dependency_pending
- B：真实成员授权/撤销、设备凭据、媒体访问策略 → dependency_pending
- 生产人脸真实 1:1 提供方未接入（C 有意 fail-closed）

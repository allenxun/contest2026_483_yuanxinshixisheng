# E C/M4 黑盒验收 —— C 8b3592e，run E-AB-20260912T090802Z-b4b4ed87

> **替身形态（doubles_pass）**：短信/会话/设备凭据/存储/人脸均为 dev 替身；种子=直连 SQL，不等于跨包真实链路。D 真实端点（方案生成、真实任务替换）与 B 真实端点（授权/成员/设备）相关场景仍 dependency_pending。

## 结算：3/14 唯一结算；1 PASS / 2 FAIL / 0 BLOCKED / 0 INFO（计数和=3==行数 3）；final_exit=1

**C/M4 黑盒验收结果：未通过**——1 PASS / 2 FAIL / 0 BLOCKED / 0 INFO。

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| SETUP | 前置：端口空闲且无同名容器 | **FAIL** | ss/docker / 1 | 环境未净 |
| CLEANUP | 按 run 标签删除 E 容器 | **FAIL** | docker rm / 1 | 容器 mvp-e-pg 不属于本 run(E-AB-20260912T090802Z-b4b4ed87)，拒绝清理 |
| CLEANUP-ports | 端口释放 | **PASS** | ss / 0 |  |

## C 缺陷清单


- **SETUP** 前置：端口空闲且无同名容器；环境未净
- **CLEANUP** 按 run 标签删除 E 容器；容器 mvp-e-pg 不属于本 run(E-AB-20260912T090802Z-b4b4ed87)，拒绝清理

## 待集成/依赖披露

- D：M3-A01 真实方案生成与任务替换链路、plan_payload 版本化白名单批准 → dependency_pending
- B：真实成员授权/撤销、设备凭据、媒体访问策略 → dependency_pending
- 生产人脸真实 1:1 提供方未接入（C 有意 fail-closed）

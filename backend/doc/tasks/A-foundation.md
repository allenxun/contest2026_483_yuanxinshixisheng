# A：工程基础与公共契约

先读 COMMON.md、上级技术/数据/详细设计第 1—4、8—12、14—15 节。此包必须通过验收后才启动 B/C/D。

## 目标与范围

在 backend/web-java、backend/worker-python、backend/contracts、backend/deploy 建立可用基础，按实际环境选择并锁定受支持版本。Java Spring Boot/MVC/JDBC，Python 显式 SQL/任务协议，一套 Flyway 迁移。业务表保持 14 张，不写 JOIN，不为每个模块创建独立服务。

交付：

1. 可构建、启动的 Java/Python 工程，有限连接池、结构化错误与 requestId、健康检查和测试命令；镜像及隔离开发环境配置。
2. 14 表 SQL 迁移、外键/关键唯一约束、检查条件、迁移测试；真实 PG 验证，不以 SQLite 替代。循环外键后置。迁移版本唯一。
3. 27 个业务 API 的 OpenAPI 基础契约、bigint 字符串、multipart、分页、错误码和任务 JSON Schema/双方契约样例。未实现业务接口不要给假 200。
4. 认证主体上下文、手机号会话/设备证明/人脸/OSS 适配端口及明确隔离的测试替身；生产配置缺能力时 fail closed。不凭任意 accountId/installationId 就认证成功，不擅自添加自建会话表。
5. T13 幂等和代次控制公共设施、媒体元数据/存储适配基础、Python T12 领取续租/过期结果约束运行时。业务 Handler 保留清晰接入点，不抢写 B/C/D 的业务。
6. Web/Worker DB 写入边界、配置样例、构建启动说明；密码放环境变量，不写真实凭据。

验收：Java/Python 测试通过；全新 PG 可迁移并重复启动无破坏；约束拒绝双占用和双记录；最小测试 job 能从 Java 契约进入 Python 并按正确代次完成；无效认证拒绝；精简 JSON 样例跨语言一致。

共享契约有设计缺口先记录合理建议；必要外部能力未定不阻止测试骨架，但明确真实接入尚未完成。不要将此包扩展成实现所有 27 个业务 API。

交付写 backend/handoffs/A.md：commit、文件归属、实际测试、B/C/D 接入方式、未决项。正常完成输出不超过 500 字。提交当前 feature，不推送、不合并。由 E 根据已提交产物验收，总协调决定进入下一阶段。
